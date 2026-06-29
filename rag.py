# SHIELD v1 - Stage 4: RAG Vector Index (ChromaDB) - Enhanced
#
# Improvements over v1:
#   1. Empty-chunk filtering         - skip chunks with < MIN_WORD_COUNT words
#   2. Long-context embedding model  - nomic-embed-text-v1.5 (8192 token limit)
#                                      replaces all-MiniLM-L6-v2 (512 tokens)
#                                      so 8 680-word annex chunks are no longer
#                                      silently truncated and half-embedded.
#   3. Summary embeddings (offline)  - Groq LLaMA4 summarises each article once;
#                                      we embed the summary, store the full text.
#                                      Search on meaning, retrieve full article.
#   4. Summary cache                 - summaries saved to JSON so re-runs never
#                                      call Groq again unless a new chunk appears.
#   5. HyDE at query time            - Groq generates a hypothetical regulatory
#                                      passage; its embedding is averaged with the
#                                      raw query embedding to bridge the vocabulary
#                                      gap between user language and legal text.
#   6. MMR (Maximum Marginal Relevance) - post-retrieval diversity filter so the
#                                      top-k results aren't all sub-sections of
#                                      the same article.
#   7. Cross-encoder re-ranking      - local cross-encoder scores each candidate
#                                      against the original user query; far more
#                                      accurate than cosine distance alone.
#   8. Metadata source filtering     - pass source_filter= to scope retrieval to
#                                      one regulation (e.g. "GDPR") at query time.
#   9. Multi-query retrieval + RRF   - multi_query_retrieve() decomposes a broad
#                                      query into focused sub-queries via Groq,
#                                      runs independent k-NN per sub-query, then
#                                      merges with Reciprocal Rank Fusion (RRF)
#                                      before MMR + re-ranking. Solves the single-
#                                      vector ceiling for queries spanning multiple
#                                      regulatory domains simultaneously.

import os
import json
import numpy as np
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Configuration
INPUT          = os.getenv("CHUNKS_PATH",       "regulatory_chunks.json")
SUMMARY_CACHE  = os.getenv("SUMMARY_CACHE_PATH", "summary_cache.json")
DB_PATH        = "./chroma_db"
COLLECTION     = "regulations"

EMBED_MODEL    = "nomic-ai/nomic-embed-text-v1.5"
RERANK_MODEL   = "cross-encoder/ms-marco-MiniLM-L-6-v2"
GROQ_MODEL     = "meta-llama/llama-4-scout-17b-16e-instruct"

TOP_K_RETRIEVE = 10
TOP_K_FINAL    = 5     # return this many after MMR + re-ranking
MMR_LAMBDA     = 0.6   # 1.0 = pure relevance, 0.0 = pure diversity
MIN_WORD_COUNT = 50    # raised from 20 — article-level chunks are never this small

# Metadata fields stored in Chroma alongside each chunk.
# All are scalar (Chroma does not accept lists).
META_FIELDS = ("source", "regulation", "article", "article_title",
               "citation", "type", "word_count")

# Maps the regulation field in regulatory_chunks.json → a URL-safe
# source string used for Chroma source_filter queries.
# Use these exact strings in verdict.py source_filter= calls.
SOURCE_NORMALISE = {
    "GDPR":            "GDPR",
    "EU AI Act":       "EU_AI_Act",
    "EU MDR 2017/745": "EU_MDR_2017_745",
    "UK MDR 2002":     "UK_MDR_2002",
    "DUAA 2025":       "DUAA_2025",
}

# Short prefix used to build article-level chunk IDs.
# e.g. EU AI Act + Art 5 → "EUAI_Art5"
REGULATION_PREFIX = {
    "GDPR":            "GDPR",
    "EU AI Act":       "EUAI",
    "EU MDR 2017/745": "EUMDR",
    "UK MDR 2002":     "UKMDR",
    "DUAA 2025":       "DUAA",
}


# Prompts

# Used at INDEX time: converts raw legal text to dense semantic summary..
SUMMARY_SYSTEM = """You are a legal document analyst specialising in EU/UK regulations.
Given the full text of a regulatory article, write a dense 3-5 sentence plain-English
summary that captures:
- What the article regulates or requires
- Who it applies to
- Key conditions, exceptions, or thresholds
- Any data types, system types, or actions explicitly mentioned

Rules:
- Do NOT mention article numbers or regulation names
- Do NOT use bullet points; write as flowing prose
- Be specific and concrete, not generic"""

# Used at QUERY time: generates a hypothetical regulatory passage so the
# query vector is anchored in legal vocabulary, not user phrasing.
# Banning article numbers eliminates hallucinated identifiers entirely.
# IMPORTANT: The prompt explicitly asks for obligations/prohibitions/conditions
# and bans vague language like "strict controls" or "subject to regulations"
# those phrases pull the vector toward definitional chunks, not operative ones.
HYDE_SYSTEM = """You are a legal document generator specialising in EU/UK regulations.
Given a compliance question, write 3-4 sentences that a relevant regulation article
would say to directly address it.

Rules:
- Do NOT mention any specific article numbers or regulation names
- Do NOT use vague language like "subject to strict controls" or "subject to regulations"
- Write specific obligations, prohibitions, or conditions (e.g. "shall be prohibited unless", "must obtain", "requires explicit consent")
- Write in the style of regulatory text
- Do NOT answer the question - write what the law would say about it"""


# Used by multi_query_retrieve() to break a broad question into focused sub-queries.
# Each sub-query should be independently answerable by a single regulatory article.
# Returning JSON keeps parsing simple and reliable.
DECOMPOSE_SYSTEM = """You are a regulatory query analyst.
A user has asked a compliance question that touches multiple regulatory topics.
Break it into 2-4 focused sub-questions, each of which a single regulation article
could answer on its own.

Return ONLY a JSON array of strings. No prose, no markdown, no explanation.
Example output: ["What consent is required to process health data?",
                 "What obligations apply to high-risk AI systems?",
                 "What are the data transfer rules between organisations?"]"""



def _groq_call(client: Groq, system: str, user: str, max_tokens: int = 400) -> str:
    """Single Groq call; low temperature for consistent legal language."""
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def generate_summary(client: Groq, chunk: dict) -> str:
    return _groq_call(
        client,
        SUMMARY_SYSTEM,
        f"Article title: {chunk.get('title', 'Unknown')}\n\n"
        f"Article text:\n{chunk['text']}",
        max_tokens=400,
    )


def generate_hyde(client: Groq, query: str) -> str:
    return _groq_call(client, HYDE_SYSTEM, f"Question: {query}", max_tokens=300)


def decompose_query(client: Groq, query: str) -> list[str]:
    """
    Ask Groq to split a multi-intent query into focused sub-queries.
    Falls back to [query] if the response is not valid JSON so the
    caller always gets a non-empty list to iterate over.
    """
    raw = _groq_call(
        client,
        DECOMPOSE_SYSTEM,
        f"Question: {query}",
        max_tokens=300,
    )
    try:
        sub_queries = json.loads(raw)
        if isinstance(sub_queries, list) and all(isinstance(q, str) for q in sub_queries):
            return sub_queries
    except (json.JSONDecodeError, ValueError):
        pass
    print(f"  [WARN] Query decomposition returned unexpected format - using original query.")
    return [query]


# Embedding helpers
# nomic-embed-text-v1.5 uses asymmetric task prefixes:
#   "search_document: " for texts being indexed
#   "search_query: "    for the query vector
# Skipping these prefixes degrades recall by 10–15% on retrieval benchmarks.

def embed_documents(model: SentenceTransformer, texts: list[str]) -> np.ndarray:
    """Embed a list of document texts (index-side)."""
    prefixed = [f"search_document: {t}" for t in texts]
    return model.encode(prefixed, normalize_embeddings=True, show_progress_bar=True)


def embed_query(model: SentenceTransformer, text: str) -> np.ndarray:
    """Embed a single query string (query-side)."""
    return model.encode(
        [f"search_query: {text}"],
        normalize_embeddings=True,
    )[0]


# MMR
def mmr(
    query_vec:      np.ndarray,
    candidate_vecs: np.ndarray,   # shape: (n_candidates, dim)
    candidates:     list[dict],
    k:              int,
    lambda_:        float,
) -> list[dict]:
    """
    Maximum Marginal Relevance - greedy selection that trades off:
        relevance  = cosine(candidate, query)
        redundancy = max cosine(candidate, already_selected)

    Score = lambda * relevance  -  (1 - lambda) * redundancy
    lambda=1 → pure relevance; lambda=0 → pure diversity.

    Vectors must already be L2-normalised (nomic does this when
    normalize_embeddings=True), so dot-product == cosine similarity.
    """
    selected: list[int] = []
    remaining = list(range(len(candidates)))

    for _ in range(min(k, len(candidates))):
        scores = []
        for i in remaining:
            relevance  = float(np.dot(query_vec, candidate_vecs[i]))
            redundancy = (
                max(float(np.dot(candidate_vecs[i], candidate_vecs[s]))
                    for s in selected)
                if selected else 0.0
            )
            scores.append(lambda_ * relevance - (1 - lambda_) * redundancy)

        best = remaining[int(np.argmax(scores))]
        selected.append(best)
        remaining.remove(best)

    return [candidates[i] for i in selected]


# Metadata
def build_metadata(chunk: dict) -> dict:
    """
    Build a flat Chroma-compatible metadata dict from an article-level chunk.

    The article-level chunk produced by aggregate_to_article_level() has:
      regulation, article, article_title, text, word_count,
      source (URL-safe, added during aggregation),
      citation (human-readable, added during aggregation)

    Chroma only accepts scalar values — no lists, no None.
    """
    return {k: chunk[k] for k in META_FIELDS
            if k in chunk and chunk[k] is not None}


# Chunk loading
def load_chunks(path: str, label: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"  [WARN] {label} not found: {path} - skipping.")
        return []
    chunks = json.load(open(path, encoding="utf-8"))
    print(f"  Loaded {len(chunks):>4} chunks from {label}")
    return chunks


def filter_empty(chunks: list[dict]) -> list[dict]:
    """
    Drop chunks whose text is blank or below MIN_WORD_COUNT.
    After article-level aggregation MIN_WORD_COUNT=50 is easy to clear,
    but the guard still catches malformed input.
    """
    valid   = [c for c in chunks
               if c.get("word_count", 0) >= MIN_WORD_COUNT
               and c.get("text", "").strip()]
    removed = len(chunks) - len(valid)
    if removed:
        dropped = [c.get("chunk_id", "?") for c in chunks
                   if c.get("word_count", 0) < MIN_WORD_COUNT
                   or not c.get("text", "").strip()]
        print(f"  [INFO] Filtered {removed} near-empty chunk(s): {dropped}")
    return valid


def deduplicate(chunks: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in chunks:
        if c["chunk_id"] not in seen:
            seen.add(c["chunk_id"])
            out.append(c)
    removed = len(chunks) - len(out)
    if removed:
        print(f"  [INFO] Removed {removed} duplicate chunk_id(s).")
    return out


def aggregate_to_article_level(raw_chunks: list[dict]) -> list[dict]:
    """
    Collapse sub-point chunks (e.g. GDPR_Art5_Para1_a, _b, _c …)
    into one chunk per article (GDPR_Art5).

    WHY: sub-point chunks average ~60 words. An 8192-token embedding
    model summarising 23 words produces a near-zero-information vector.
    Article-level chunks average 867 words — the model can extract
    meaningful legal semantics.

    Output chunk schema:
      chunk_id     : e.g. "GDPR_Art5"
      regulation   : original regulation name  e.g. "GDPR"
      source       : URL-safe key              e.g. "GDPR"   (for Chroma filter)
      article      : article identifier        e.g. "5"
      article_title: title of the article
      citation     : human-readable cite       e.g. "GDPR, Article 5 — Principles..."
      text         : all sub-point text joined by newline
      type         : "article"
      word_count   : total word count across sub-points
    """
    from collections import defaultdict, OrderedDict

    # Group sub-points by (regulation, article) preserving document order
    groups: dict[tuple, list] = OrderedDict()
    for c in raw_chunks:
        reg = c.get("regulation", "?")
        art = c.get("article", "?")
        key = (reg, art)
        groups.setdefault(key, []).append(c)

    aggregated = []
    for (reg, art), sub_chunks in groups.items():
        prefix = REGULATION_PREFIX.get(reg, reg.replace(" ", "").replace("/", ""))
        # Sanitise article identifier for use in chunk_id
        art_safe = art.replace(" ", "").replace("/", "-").replace(".", "_")
        chunk_id = f"{prefix}_Art{art_safe}"

        # Use article_title from the first sub-chunk
        article_title = sub_chunks[0].get("article_title", "")

        # Concatenate sub-point texts in document order
        texts = [c["text"].strip() for c in sub_chunks if c.get("text", "").strip()]
        full_text = "\n".join(texts)

        source  = SOURCE_NORMALISE.get(reg, reg.replace(" ", "_").replace("/", "_"))
        cite_art = f"Article {art}" if not art.startswith(("Annex", "Part", "S", "Schedule")) else art
        citation = f"{reg}, {cite_art}"
        if article_title:
            citation += f" \u2014 {article_title}"

        aggregated.append({
            "chunk_id":     chunk_id,
            "regulation":   reg,
            "source":       source,
            "article":      art,
            "article_title": article_title,
            "citation":     citation,
            "text":         full_text,
            "type":         "article",
            "word_count":   sum(c.get("word_count", 0) for c in sub_chunks),
        })

    return aggregated


# Summary cache
def load_summary_cache(path: str) -> dict:
    if os.path.exists(path):
        cache = json.load(open(path, encoding="utf-8"))
        print(f"  Loaded {len(cache)} cached summaries from {path}")
        return cache
    return {}


def save_summary_cache(cache: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    json.dump(cache, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


# Indexing
def build_index(
    chunks:      list[dict],
    embed_model: SentenceTransformer,
    groq_client: Groq,
    col,
) -> None:
    """
    For each chunk:
      1. Generate a plain-English summary via Groq (cached after first run).
      2. Embed the summary  → this is the search vector.
      3. Store the full article text as the Chroma document.

    Result: semantic search finds articles by meaning;
            the LLM receives the complete, uncut article text.
    """
    # Summaries
    cache        = load_summary_cache(SUMMARY_CACHE)
    new_count    = 0
    missing      = [c for c in chunks if c["chunk_id"] not in cache]

    if missing:
        print(f"\n  Generating {len(missing)} new summaries via Groq "
              f"({len(chunks) - len(missing)} already cached)...")
        for i, chunk in enumerate(missing, 1):
            cid = chunk["chunk_id"]
            print(f"    [{i:>3}/{len(missing)}] {cid}")
            cache[cid] = generate_summary(groq_client, chunk)
            new_count += 1
        save_summary_cache(cache, SUMMARY_CACHE)
        print(f"  Saved {new_count} new summaries → {SUMMARY_CACHE}")
    else:
        print("  All summaries loaded from cache. No Groq calls needed.")

    # Summaries
    summaries  = [cache[c["chunk_id"]] for c in chunks]  
    full_texts = [c["text"]            for c in chunks]  

    # Embed summaries, not full texts - this is the core of the improvement.
    print(f"\n  Embedding {len(summaries)} summaries with '{EMBED_MODEL}'...")
    embeddings = embed_documents(embed_model, summaries)  

    # ── Upsert ────────────────────────────────────────────────────
    # embeddings = summary vectors (for search)
    # documents  = full article texts (returned to caller/LLM)
    col.upsert(
        ids        = [c["chunk_id"] for c in chunks],
        embeddings = embeddings.tolist(),
        documents  = full_texts,
        metadatas  = [build_metadata(c) for c in chunks],
    )
    print(f"\n  Collection '{COLLECTION}' now holds {col.count()} chunks at {DB_PATH}")


# Query
def query_index(
    user_query:     str,
    col,
    embed_model:    SentenceTransformer,
    reranker:       CrossEncoder,
    groq_client:    Groq,
    source_filter:  str | None = None,  
    top_k_retrieve: int        = TOP_K_RETRIEVE,
    top_k_final:    int        = TOP_K_FINAL,
) -> list[dict]:
    """
    Full retrieval pipeline:
      Step 1 - HyDE       : LLM generates hypothetical regulatory text.
      Step 2 - Query vec  : Average (raw query + hypothetical) embeddings.
      Step 3 - k-NN       : ChromaDB retrieves top_k_retrieve candidates.
      Step 4 - MMR        : Diversify using stored embeddings (no extra API call).
      Step 5 - Re-rank    : Cross-encoder re-scores against original user query.

    Returns top_k_final results sorted by re-rank score (descending).
    Each result dict contains full article text, metadata, and both scores.
    """

    # Step 1 - HyDE
    print(f"  [HyDE] Generating hypothetical regulatory passage...")
    hypothetical = generate_hyde(groq_client, user_query)
    print(f"  [HyDE] \"{hypothetical[:100]}...\"")

    # Step 2 - Combined query vector
    # Averaging: hypothetical pulls the vector toward legal vocabulary;
    # raw query keeps it grounded to the user's actual intent.
    # Re-normalise after averaging so cosine distances remain valid.
    q_vec    = embed_query(embed_model, user_query)
    hyde_vec = embed_query(embed_model, hypothetical)
    combined = (q_vec + hyde_vec) / 2.0
    combined = combined / np.linalg.norm(combined)

    # Step 3 - ChromaDB k-NN
    # include="embeddings" fetches stored vectors so MMR can use them without a second embedding call.
    where = {"source": source_filter} if source_filter else None
    res   = col.query(
        query_embeddings = [combined.tolist()],
        n_results        = top_k_retrieve,
        where            = where,
        include          = ["documents", "metadatas", "distances", "embeddings"],
    )

    ids        = res["ids"][0]
    docs       = res["documents"][0]
    metas      = res["metadatas"][0]
    distances  = res["distances"][0]
    stored_vecs = np.array(res["embeddings"][0])  # reuse for MMR - free

    candidates = [
        {"id": i, "text": d, "meta": m, "distance": dist}
        for i, d, m, dist in zip(ids, docs, metas, distances)
    ]

    # Step 4 - MMR (uses stored_vecs, no extra embedding call)
    candidates = mmr(
        query_vec      = combined,
        candidate_vecs = stored_vecs,
        candidates     = candidates,
        k              = min(top_k_final + 3, len(candidates)),
        lambda_        = MMR_LAMBDA,
    )

    # Step 5 - Cross-encoder re-ranking
    # Cross-encoder sees (query, document) jointly - much more accurate
    # than cosine similarity. We truncate document text to 512 chars
    # for the cross-encoder (it has its own token limit) but the full
    # text is still in c["text"] for the LLM.
    #
    # NOTE on negative scores: ms-marco was trained on web search passages.
    # Legal text sits outside that distribution so raw logit scores are
    # negative across the board. This is expected - what matters is the
    # relative ordering (rank), not the absolute value.
    # We sigmoid-normalise to [0, 1] so scores are readable in the UI.
    pairs  = [[user_query, c["text"][:512]] for c in candidates]
    raw_scores = reranker.predict(pairs)

    def sigmoid(x: float) -> float:
        return float(1 / (1 + np.exp(-x)))

    for c, s in zip(candidates, raw_scores):
        c["rerank_score"]      = float(s)
        c["rerank_score_norm"] = sigmoid(float(s))

    # Fallback: if the cross-encoder is not confident about any candidate
    # (all norm scores below LOW_CONF_THRESHOLD), it means we're outside its
    # training distribution (legal text vs web passages). In that case, trust
    # cosine distance ordering instead of a confused re-ranker.
    LOW_CONF_THRESHOLD = 0.1
    max_norm = max(c["rerank_score_norm"] for c in candidates)
    if max_norm < LOW_CONF_THRESHOLD:
        print(f"  [Re-rank] Low confidence (max_norm={max_norm:.3f}) - "
              f"falling back to cosine distance ordering.")
        candidates.sort(key=lambda x: x["distance"])    # lower dist = more similar
    else:
        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)

    return candidates[:top_k_final]


# Reciprocal Rank Fusion
def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]],
    k: int = 60,
) -> list[dict]:
    """
    Merge multiple ranked candidate lists into one using RRF.

    RRF score for a document = Σ  1 / (k + rank_i)
    where rank_i is its position in the i-th ranked list (1-based).
    k=60 is the standard value from the original RRF paper (Cormack 2009).

    Why RRF instead of score averaging?
    - Each sub-query's cosine distances are on different scales.
    - RRF only uses rank position - scale-invariant and robust.
    - A document appearing in the top-3 of two lists consistently
      outscores one that is top-1 in only one list.
    """
    scores: dict[str, float] = {}
    docs_by_id: dict[str, dict] = {}

    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            doc_id = item["id"]
            scores[doc_id]    = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            docs_by_id[doc_id] = item   # last-write is fine; content is identical

    merged = sorted(docs_by_id.values(), key=lambda x: scores[x["id"]], reverse=True)
    for item in merged:
        item["rrf_score"] = scores[item["id"]]
    return merged


# Multi-query retrieval
def multi_query_retrieve(
    user_query:     str,
    col,
    embed_model:    SentenceTransformer,
    reranker:       CrossEncoder,
    groq_client:    Groq,
    source_filter:  str | None = None,
    top_k_retrieve: int        = TOP_K_RETRIEVE,
    top_k_final:    int        = TOP_K_FINAL,
) -> list[dict]:
    """
    Handles multi-intent queries that span more than one regulatory domain.

    Pipeline:
      Step 1 - Decompose  : Groq splits the query into 2-4 focused sub-queries.
      Step 2 - Per-query  : Each sub-query runs through HyDE → embed → k-NN
                            independently (standard query_index internals, minus
                            the final MMR/re-rank so we gather all raw candidates).
      Step 3 - RRF merge  : Reciprocal Rank Fusion combines all candidate lists
                            into one ranked pool without relying on raw distances.
      Step 4 - MMR        : Diversity pass over the merged pool.
      Step 5 - Re-rank    : Cross-encoder re-scores against the ORIGINAL user
                            query (not the sub-queries) for final ordering.

    Falls back to single query_index() if decomposition returns only 1 sub-query.
    """

    # Step 1 - Decompose
    print(f"  [Decompose] Breaking query into sub-queries...")
    sub_queries = decompose_query(groq_client, user_query)
    print(f"  [Decompose] {len(sub_queries)} sub-queries:")
    for i, sq in enumerate(sub_queries, 1):
        print(f"    {i}. \"{sq}\"")

    # Single sub-query → no benefit from multi-query path
    if len(sub_queries) == 1:
        return query_index(user_query, col, embed_model, reranker, groq_client,
                           source_filter, top_k_retrieve, top_k_final)

    # Step 2 - Per-sub-query k-NN (raw candidates, no MMR/re-rank yet)
    where = {"source": source_filter} if source_filter else None
    all_ranked_lists: list[list[dict]] = []

    for sq in sub_queries:
        print(f"\n  [HyDE] Sub-query: \"{sq[:70]}\"")
        hypothetical = generate_hyde(groq_client, sq)
        print(f"  [HyDE] → \"{hypothetical[:80]}...\"")

        q_vec    = embed_query(embed_model, sq)
        hyde_vec = embed_query(embed_model, hypothetical)
        combined = (q_vec + hyde_vec) / 2.0
        combined = combined / np.linalg.norm(combined)

        res = col.query(
            query_embeddings = [combined.tolist()],
            n_results        = top_k_retrieve,
            where            = where,
            include          = ["documents", "metadatas", "distances", "embeddings"],
        )

        ranked = [
            {"id": i, "text": d, "meta": m, "distance": dist,
             "embedding": emb}
            for i, d, m, dist, emb in zip(
                res["ids"][0], res["documents"][0], res["metadatas"][0],
                res["distances"][0], res["embeddings"][0]
            )
        ]
        all_ranked_lists.append(ranked)

    # Step 3 - RRF merge
    merged = reciprocal_rank_fusion(all_ranked_lists)
    print(f"\n  [RRF] Merged pool: {len(merged)} unique candidates")

    # Step 4 - MMR over merged pool
    # Needed embeddings for MMR - pull from the stored embedding on each item.
    merged_vecs = np.array([item["embedding"] for item in merged])
    # Use the original query embedding as the relevance anchor for MMR
    orig_vec = embed_query(embed_model, user_query)

    diverse = mmr(
        query_vec      = orig_vec,
        candidate_vecs = merged_vecs,
        candidates     = merged,
        k              = min(top_k_final + 3, len(merged)),
        lambda_        = MMR_LAMBDA,
    )

    # Step 5 - Cross-encoder re-ranking against the ORIGINAL query
    pairs      = [[user_query, c["text"][:512]] for c in diverse]
    raw_scores = reranker.predict(pairs)

    def sigmoid(x: float) -> float:
        return float(1 / (1 + np.exp(-x)))

    for c, s in zip(diverse, raw_scores):
        c["rerank_score"]      = float(s)
        c["rerank_score_norm"] = sigmoid(float(s))

    # Fallback: if cross-encoder is not confident about any candidate,
    # trust RRF score (consistent cross-query relevance) over a confused re-ranker.
    # This prevents a definition chunk from beating a substantively relevant article
    # on keyword overlap alone.
    LOW_CONF_THRESHOLD = 0.1
    max_norm = max(c["rerank_score_norm"] for c in diverse)
    if max_norm < LOW_CONF_THRESHOLD:
        print(f"  [Re-rank] Low confidence (max_norm={max_norm:.3f}) - "
              f"falling back to RRF score ordering.")
        diverse.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
    else:
        diverse.sort(key=lambda x: x["rerank_score"], reverse=True)

    return diverse[:top_k_final]
def main():
    print("=" * 65)
    print("  SHIELD - RAG Vector Index (ChromaDB) - Phase 3")
    print("=" * 65)

    # Load raw sub-point chunks
    print("\n[1/5] Loading chunk file...")
    raw_chunks = load_chunks(INPUT, "regulatory_chunks.json")
    if not raw_chunks:
        print("[ERROR] No chunks loaded. Exiting.")
        return

    # Aggregate sub-point → article level
    print("\n[2/5] Aggregating sub-point chunks to article level...")
    all_chunks = aggregate_to_article_level(raw_chunks)
    all_chunks = filter_empty(all_chunks)
    all_chunks = deduplicate(all_chunks)

    from collections import Counter
    tally = Counter(c["regulation"] for c in all_chunks)
    print(f"\n  Ready to index: {len(all_chunks)} article-level chunks")
    for reg, n in sorted(tally.items()):
        print(f"    {reg:<26} {n:>2} articles")

    # Load models
    print(f"\n[3/5] Loading models...")
    print(f"  Embedding model : {EMBED_MODEL}")
    embed_model = SentenceTransformer(EMBED_MODEL, trust_remote_code=True)
    print(f"  Re-ranker       : {RERANK_MODEL}")
    reranker    = CrossEncoder(RERANK_MODEL)
    print(f"  Groq LLM        : {GROQ_MODEL}")
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # ChromaDB
    print(f"\n[4/5] Initialising ChromaDB at '{DB_PATH}'...")
    client = chromadb.PersistentClient(path=DB_PATH)
    col    = client.get_or_create_collection(
        name     = COLLECTION,
        metadata = {"hnsw:space": "cosine"},
    )

    # Build index
    print(f"\n[5/5] Building index...")
    build_index(all_chunks, embed_model, groq_client, col)

    # ── Self-tests covering all 5 regulations ────────────────────────────────
    print(f"\n{'=' * 65}")
    print("  Self-test — one focused query per regulation")
    print(f"{'=' * 65}")

    focused_tests = [
        (
            "What lawful basis is required to process health data under GDPR?",
            "GDPR",
        ),
        (
            "What obligations apply to high-risk AI systems under the EU AI Act?",
            "EU_AI_Act",
        ),
        (
            "What clinical evaluation requirements apply to medical device software?",
            "EU_MDR_2017_745",
        ),
        (
            "What conformity assessment requirements apply under the UK MDR 2002?",
            "UK_MDR_2002",
        ),
        (
            "What automated decision-making rules apply under the DUAA 2025?",
            "DUAA_2025",
        ),
    ]

    for probe, src_filter in focused_tests:
        print(f"\nQuery : \"{probe}\"")
        print(f"Filter: source = '{src_filter}'")
        print("-" * 65)
        results = query_index(
            user_query    = probe,
            col           = col,
            embed_model   = embed_model,
            reranker      = reranker,
            groq_client   = groq_client,
            source_filter = src_filter,
        )
        for rank, r in enumerate(results, 1):
            citation = r["meta"].get("citation", "")[:60]
            print(f"  #{rank}  norm={r['rerank_score_norm']:.3f}  "
                  f"raw={r['rerank_score']:+.2f}  "
                  f"{r['id']:<22}  {citation}")

    # Multi-regulation query (no source filter)
    print(f"\nQuery (multi-regulation, no filter):")
    q_multi = ("Can my elderly-care assistant store fall-risk predictions "
               "and share them with caregivers?")
    print(f"  \"{q_multi}\"")
    print("-" * 65)
    results = multi_query_retrieve(q_multi, col, embed_model, reranker, groq_client)
    for rank, r in enumerate(results, 1):
        citation = r["meta"].get("citation", "")[:60]
        print(f"  #{rank}  norm={r['rerank_score_norm']:.3f}  "
              f"rrf={r.get('rrf_score', 0):.4f}  "
              f"{r['id']:<22}  {citation}")

    print("\n" + "=" * 65)
    print("  Done.")
    print("=" * 65)


if __name__ == "__main__":
    main()