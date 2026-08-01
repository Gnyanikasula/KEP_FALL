# KEP_FALL v1 - Stage 6: Hybrid Retrieval + LLM Verdict


import os
import sys
import re
import json
import time
from dataclasses import dataclass, field
from typing import Optional, List, Literal
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator, ValidationError

from neo4j import GraphDatabase
import chromadb
from sentence_transformers import SentenceTransformer

from kep_fall.phase_d_engine.router import understand_query, QueryPayload
from kep_fall.phase_d_engine import graph_store
from kep_fall import config
from kep_fall import citation as _cite

load_dotenv()

# Config
# MODEL          = "openai/gpt-oss-120b"
# MODEL          = "openai/gpt-oss-120b"
MODEL          = config.LLM_MODEL
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
# CHROMA_PATH    = "./chroma_db"
# COLLECTION     = "regulations"
CHROMA_PATH    = config.CHROMA_PATH
COLLECTION     = config.CHROMA_COLLECTION
# Must match the model used in rag.py to build the index, querying with a
# different model compares incompatible vector spaces.
# EMBED_MODEL    = "nomic-ai/nomic-embed-text-v1.5"
EMBED_MODEL    = config.EMBED_MODEL


# EMBED_MODEL = "jinaai/jina-embeddings-v2-base-en"
MAX_RETRIES    = 2
RETRY_DELAY    = 2

# Free-tier token budget (gny_v3)
# openai/gpt-oss-120b free tier: 30 RPM, 8,000 TPM, 200,000 TPD.
# The whole retrieved chunk set is kept (recall unchanged vs the gny_v2
# baseline), only per-chunk excerpt depth is tiered. The RAG_HEAD_N chunks
# with the smallest embedding distance keep RAG_HEAD_CHARS characters, the
# rest keep RAG_TAIL_CHARS. Measured: mean ~5.8K, max ~6.7K tokens per call
# including output, leaving headroom for reasoning tokens.
RAG_HEAD_N     = int(os.getenv("KEP_FALL_RAG_HEAD_N", "8"))
RAG_HEAD_CHARS = int(os.getenv("KEP_FALL_RAG_HEAD_CHARS", "1200"))
RAG_TAIL_CHARS = int(os.getenv("KEP_FALL_RAG_TAIL_CHARS", "400"))

# Reasoning tokens count towards TPM, so cap them and cap the completion.
REASONING_EFFORT      = os.getenv("KEP_FALL_REASONING_EFFORT", "low")
MAX_COMPLETION_TOKENS = int(os.getenv("KEP_FALL_MAX_COMPLETION", "1200"))

# 429 / rate-limit backoff. TPM is a rolling window, so waiting genuinely
# clears it, unlike a malformed-JSON error, which needs a re-prompt.
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_DELAY   = 8
_HISTORY_TURNS = int(os.getenv("KEP_FALL_HISTORY_TURNS", "6"))  # 6 msgs = 3 exchanges
GENERIC_WORDS  = {"data", "personal", "information", "the", "a", "an"}


def _create_with_backoff(client, **kwargs):
    """Groq chat completion with rate-limit backoff.

    Free-tier TPM is 8,000 and shared across the whole organisation, so two
    concurrent demo users can trip a 429 even though nothing is wrong. A
    rate-limit error is transient and worth waiting out; anything else gets
    re-raised immediately.
    """
    delay = RATE_LIMIT_DELAY
    for attempt in range(1 + RATE_LIMIT_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as err:
            msg = str(err).lower()
            transient = ("rate_limit" in msg or "429" in msg
                         or "too large" in msg or "413" in msg)
            if not transient or attempt == RATE_LIMIT_RETRIES:
                raise
            print(f"[rate-limit] attempt {attempt + 1}, waiting {delay}s")
            time.sleep(delay)
            delay *= 2


# Lazy singletons
_DRIVER         = None
_COLLECTION     = None
_EMBED_INSTANCE = None


def _driver():
    global _DRIVER
    if _DRIVER is None:
        # Phase 0 (survival): fail fast on a paused/unreachable Aura instead
        # of hanging on the driver's 30-60s defaults. connection_timeout
        # bounds the socket connect, connection_acquisition_timeout bounds
        # waiting for a pooled connection, max_transaction_retry_time caps
        # managed-transaction retries. All set to config.NEO4J_TIMEOUT (3s)
        # so the circuit breaker in graph_store trips to the local
        # read-model within a few seconds instead of blocking the request
        # thread.
        _DRIVER = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD),
            connection_timeout=config.NEO4J_TIMEOUT,
            connection_acquisition_timeout=config.NEO4J_TIMEOUT,
            max_transaction_retry_time=config.NEO4J_TIMEOUT,
        )
    return _DRIVER


def _store():
    """
    Breaker-wrapped graph access: Neo4j Aura primary, local read-model
    fallback. Both stores return rows in the same shape the old direct
    Cypher calls did, so nothing downstream of kg_retrieve / _bridge_hop /
    _fetch_by_article needs to change.
    """
    return graph_store.get_store(
        driver_factory=_driver,
        database=NEO4J_DATABASE,
        bridge_cypher=_BRIDGE_CYPHER,
        by_article_cypher=_BY_ARTICLE_CYPHER,
    )


def _collection():
    global _COLLECTION
    if _COLLECTION is None:
        _COLLECTION = chromadb.PersistentClient(path=CHROMA_PATH).get_collection(COLLECTION)
    return _COLLECTION


def _embed_model():
    global _EMBED_INSTANCE
    if _EMBED_INSTANCE is None:
        _EMBED_INSTANCE = SentenceTransformer(EMBED_MODEL, trust_remote_code=True)
    return _EMBED_INSTANCE

# def _embed_model():
#     global _EMBED_INSTANCE
#     if _EMBED_INSTANCE is None:
#         _EMBED_INSTANCE = SentenceTransformer(
#             EMBED_MODEL, trust_remote_code=True)
#     return _EMBED_INSTANCE
def _embed(text: str) -> list[float]:
    """Embed a single query string with nomic's required search_query prefix."""
    vec = _embed_model().encode(
        [f"search_query: {text}"], normalize_embeddings=True
    )
    return vec[0].tolist()
# def _embed(text: str) -> list[float]:
#     return _embed_model().encode(
#         [text], normalize_embeddings=True
#     )[0].tolist()


# Verdict schema
class Citation(BaseModel):
    """
    Structured citation. The evaluator reads this, not the prose.

    Scraping article numbers out of `reasoning` with a regex is lossy and
    was the source of the DUAA scoring bug (bare "22" matched out of
    "Article 22C"). Making the model emit the citation as data removes the
    regex from the primary scoring path entirely.
    """
    regulation: Optional[str] = None   # "GDPR" | "EU AI Act" | "DUAA 2025" | ...
    provision:  str                    # "Article 9" | "Article 22C" | "Regulation 8" | "Annex I"


class Verdict(BaseModel):
    verdict:    Literal["Allowed", "Conditionally Allowed", "Prohibited",
                        "Unclear", "Informational", "Out of Scope"]
    rules:      List[str]
    reasoning:  str
    conditions: List[str] = []
    confidence: int
    # Optional so every existing caller and canned response keeps working
    # unchanged. Absent -> the evaluator falls back to prose extraction.
    citations:  List[Citation] = []

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v: int) -> int:
        return max(0, min(100, int(v)))


# Legal term expansion
# Bridges user language ("health data") to exact regulatory vocabulary
# ("data concerning health", "special categories") so RAG finds the right
# chunks even when the user's phrasing doesn't match the regulation's wording.
_LEGAL_TERM_MAP: dict[str, list[str]] = {
    "health data":          ["data concerning health", "special categories",
                             "clinical data", "medical data", "health information"],
    "medical data":         ["data concerning health", "special categories",
                             "clinical data", "health status"],
    "personal data":        ["personal data", "data subject", "natural person",
                             "identifiable person"],
    "biometric data":       ["biometric data", "facial images", "dactyloscopic",
                             "unique identification"],
    "genetic data":         ["genetic data", "inherited characteristics",
                             "biological sample"],
    "consent":              ["explicit consent", "freely given", "specific informed",
                             "unambiguous indication", "withdrawal of consent"],
    "lawful basis":         ["lawful basis", "legal basis", "Article 6",
                             "legitimate interests", "contractual necessity",
                             "legal obligation", "vital interests", "public task"],
    "explicit consent":     ["explicit consent", "Article 9(2)(a)",
                             "freely given specific informed unambiguous"],
    "right to erasure":     ["right to erasure", "right to be forgotten",
                             "Article 17", "erase personal data"],
    "right of access":      ["right of access", "Article 15", "access to data"],
    "data portability":     ["data portability", "Article 20", "structured format"],
    "automated decisions":  ["automated processing", "solely automated",
                             "legal effects", "profiling", "Article 22"],
    "profiling":            ["profiling", "automated processing", "evaluate aspects",
                             "predict behaviour", "Article 22"],
    "data minimisation":    ["data minimisation", "adequate relevant limited",
                             "Article 5(1)(c)", "minimum necessary"],
    "purpose limitation":   ["purpose limitation", "Article 5(1)(b)",
                             "specified explicit legitimate purposes"],
    "storage limitation":   ["storage limitation", "Article 5(1)(e)",
                             "no longer than necessary", "retention period"],
    "transparency":         ["transparency", "Article 5(1)(a)", "transparent manner",
                             "clear plain language"],
    "privacy by design":    ["data protection by design", "Article 25",
                             "privacy by design", "pseudonymisation"],
    "dpia":                 ["data protection impact assessment", "Article 35",
                             "DPIA", "high risk processing", "prior consultation"],
    "data breach":          ["personal data breach", "Article 33", "Article 34",
                             "notification", "72 hours", "supervisory authority"],
    "data transfer":        ["transfer personal data", "third country",
                             "adequacy decision", "Article 44", "Article 45"],
    "high risk ai":         ["high-risk AI system", "Annex III", "Article 6",
                             "safety component", "significant harm",
                             "fundamental rights", "Chapter III Section 2"],
    "prohibited ai":        ["prohibited AI practices", "Article 5",
                             "subliminal techniques", "social scoring",
                             "real-time biometric", "manipulation"],
    "general purpose ai":   ["general-purpose AI model", "GPAI", "Article 51",
                             "systemic risk"],
    "human oversight":      ["human oversight", "Article 14", "natural person",
                             "monitor functioning", "override halt"],
    "transparency ai":      ["transparency obligations", "Article 50", "Article 13",
                             "instructions for use", "technical documentation"],
    "technical documentation": ["technical documentation", "Annex IV", "Article 11",
                                "general description", "development process"],
    "risk management":      ["risk management system", "Article 9",
                             "identify analyse estimate", "residual risk"],
    "post market monitoring": ["post-market monitoring", "Article 72",
                               "market surveillance", "serious incident"],
    "medical device":       ["medical device", "Article 2(1)", "intended purpose",
                             "diagnosis prevention monitoring"],
    "software medical device": ["software", "SaMD", "Recital 19",
                                "medical purpose", "standalone software",
                                "Rule 11", "Annex VIII"],
    "device classification":["device classification", "Annex VIII", "Rule 11",
                             "Class IIa", "Class IIb", "Class III"],
    "clinical evaluation":  ["clinical evaluation", "Article 61", "Annex XIV",
                             "clinical data", "clinical evidence"],
    "manufacturer obligations": ["manufacturer", "Article 10",
                                 "quality management system", "post-market surveillance",
                                 "technical documentation"],
    "uk mdr":               ["UK MDR 2002", "SI 2002/618", "MHRA", "Great Britain",
                             "UK Conformity Assessed", "UKCA"],
    "controller":           ["controller", "Article 4(7)", "determines purposes"],
    "processor":            ["processor", "Article 4(8)", "processes on behalf",
                             "Article 28", "data processing agreement"],
    "anonymisation":        ["anonymisation", "pseudonymisation", "Article 4(5)",
                             "re-identification", "cannot be attributed"],
        # Extra retrieval terms
    "location data":        ["location data", "movements", "tracking"],
    "financial data":       ["financial interests", "economic situation",
                             "creditworthiness"],
    "right to object":      ["right to object", "Article 21", "direct marketing",
                             "legitimate grounds"],
    "accuracy":             ["accuracy", "Article 5(1)(d)", "kept up to date",
                             "inaccurate data rectified"],
    "accountability":       ["accountability", "Article 5(2)",
                             "demonstrate compliance", "controller responsible"],
    "integrity confidentiality": ["integrity confidentiality", "Article 5(1)(f)",
                                  "appropriate security", "encryption",
                                  "unauthorised access"],
    "data protection officer": ["data protection officer", "DPO", "Article 37",
                                "Article 38", "Article 39"],
    "security":             ["security of processing", "Article 32",
                             "technical organisational measures", "encryption",
                             "pseudonymisation", "confidentiality integrity"],
    "conformity assessment": ["conformity assessment", "Article 43",
                              "notified body", "EU declaration of conformity",
                              "Article 47", "CE marking"],
    "ce marking":           ["CE marking", "conformity assessment",
                             "notified body", "Article 52",
                             "declaration of conformity"],
    "vigilance":            ["vigilance", "Article 87", "serious incident",
                             "field safety corrective action", "FSCA",
                             "competent authority notification"],
    "unique device identifier": ["unique device identifier", "UDI",
                                 "Article 27", "EUDAMED", "traceability"],
    "mhra":                 ["MHRA", "UK MDR 2002", "competent authority",
                             "Great Britain market"],
    "supervisory authority": ["supervisory authority", "data protection authority",
                              "ICO", "CNIL", "Article 51", "Article 55"],
    "legitimate interests": ["legitimate interests", "Article 6(1)(f)",
                             "balancing test", "override interests"],
    # DUAA 2025 terms
    "duaa":                 ["Data Use and Access Act", "DUAA 2025", "s.80",
                             "Article 22A", "Article 22B", "Article 22C",
                             "Article 22D", "Schedule 6"],
    "automated significant decision": ["significant decision", "solely automated",
                                       "legal effect", "similarly significant effect",
                                       "opt out", "human review", "s.80 Art22A",
                                       "Art22B restrictions", "Art22C safeguards"],
    "data intermediary":    ["data intermediary", "data sharing", "Schedule 6",
                             "recognised data altruism organisation",
                             "data intermediary services"],
    "uk automated decisions": ["automated processing significant", "opt-out right",
                               "human review request", "Article 22A", "Article 22B"],
}


def _expand_legal_terms(text: str) -> list[str]:
    """Return expanded regulatory vocabulary for any known concept in the text."""
    text_lower = text.lower()
    expansions: list[str] = []
    seen: set[str] = set()
    for user_term, legal_synonyms in _LEGAL_TERM_MAP.items():
        if any(w in text_lower for w in user_term.split()):
            for s in legal_synonyms:
                if s not in seen:
                    seen.add(s)
                    expansions.append(s)
    return expansions


# Phase 3: KG retrieval helpers

# Retrieval: Knowledge Graph
# def _kg_keyword(text: str) -> str:
#     """Strip generic stop-words and return the first meaningful keyword."""
#     words = [w for w in text.lower().split() if w not in GENERIC_WORDS]
#     return words[0] if words else text.lower().split()[0]
_KG_STOPWORDS = {
    "data", "personal", "information", "the", "a", "an", "of", "for", "and",
    "or", "to", "in", "on", "under", "with", "system", "systems", "processing",
}

def _kg_keywords(*sources: str) -> list[str]:
    """
    Builds a keyword list for graph anchoring from any number of payload fields.

    Node labels are PascalCase concatenations ('LawfulnessFairnessAndTransparency',
    'LegalBasis') and predicates are camelCase ('hasLegalBasis'). The Cypher
    match is a lowercased substring CONTAINS. So for the phrase "legal basis":

        'legal basis' in 'legalbasis'    -> False   (spaces kill it)
        'legalbasis'  in 'legalbasis'    -> True
        'legal'       in 'haslegalbasis' -> True

    v1 emitted only the spaced phrase and the individual words, so multi-word
    concepts never matched a node label. We now emit, per source:
      - the spaced phrase          'legal basis'
      - the de-spaced phrase       'legalbasis'      <- new, matches node labels
      - each meaningful word >= 4  'legal', 'basis'  <- matches predicates
    Deduplicated, stopwords removed, order preserved for stable Cypher.
    """
    seen: set[str] = set()
    out: list[str] = []
    for src_field in sources:
        if not src_field:
            continue
        phrase = " ".join(src_field.lower().split())
        words = [w.strip(".,;:()") for w in phrase.split()]
        despaced = "".join(w for w in words if w not in _KG_STOPWORDS)

        candidates = [phrase, despaced] + words
        for c in candidates:
            c = c.strip(".,;:()")
            if len(c) >= 4 and c not in _KG_STOPWORDS and c not in seen:
                seen.add(c)
                out.append(c)
    return out


def _rank_triples(rows: list[dict], keywords: list[str]) -> list[dict]:
    """
    Ranks retrieved triples by how well they match the query, then by the
    extraction confidence and whether the endpoints are ontology-typed.

    Why: the Cypher returns up to 50 rows in arbitrary keyword-match order.
    Dumping 50 triples into the prompt dilutes the context with edges from
    unrelated articles, which is what makes the hybrid arm underperform
    rag_only. Ranking doesn't add information, it just orders what was
    already retrieved. The cut-off itself is exposed as `top_k` so it can be
    ablated rather than silently tuned.
    """
    def score(r: dict) -> tuple:
        hay = " ".join(str(r.get(f) or "").lower()
                       for f in ("subject", "object", "predicate",
                                 "subject_uri", "object_uri"))
        matches = sum(1 for kw in keywords if kw in hay)
        typed = bool(r.get("subject_typed")) + bool(r.get("object_typed"))
        return (matches, r.get("confidence") or 0.0, typed)

    return sorted(rows, key=score, reverse=True)


def _article_id_to_citation(article_id: str) -> str:
    """
    Converts a Phase 2 article_id into a human-readable citation string.
    Examples:
      'GDPR__Art6'               -> 'GDPR, Article 6'
      'EU AI Act__Art5'          -> 'EU AI Act, Article 5'
      'EU AI Act__Art6_Para1_a'  -> 'EU AI Act, Article 6(1)(a)'
    """
    if not article_id:
        return ""
    parts = article_id.split("__", 1)
    if len(parts) != 2:
        return article_id
    reg, art = parts
    # "Art6" -> "Article 6"
    art = re.sub(r"^Art(\d+)", r"Article \1", art)
    # "_Para1" -> "(1)"
    art = re.sub(r"_Para(\d+)", r"(\1)", art)
    # remaining "_a" / "_b" sub-points -> "(a)" / "(b)"
    art = re.sub(r"_([a-z])$", r"(\1)", art)
    # anything else with underscores -> spaces
    art = art.replace("_", " ")
    return f"{reg}, {art}"


_BRIDGE_CYPHER = """
    // Second hop: for each anchor concept (matched by label OR shared URI),
    // pull edges in OTHER regulations that touch the SAME concept node.
    // This is what turns single-hop lookup into cross-regulation traversal:
    // e.g. anchor 'AutomatedDecision' in GDPR -> its DUAA edges.
    UNWIND $anchor_labels AS alabel
    MATCH (s:Concept)-[r:REL]->(o:Concept)
    WHERE (toLower(s.label) = toLower(alabel) OR toLower(o.label) = toLower(alabel))
      AND NOT r.regulation IN $seen_regs
    RETURN s.label          AS subject,
           s.uri            AS subject_uri,
           s.typed          AS subject_typed,
           o.typed          AS object_typed,
           s.typed          AS typed,
           r.predicate      AS predicate,
           o.label          AS object,
           o.uri            AS object_uri,
           r.regulation     AS regulation,
           r.article_id     AS article_id,
           r.canonical_id   AS canonical_id,
           r.chunk_ids      AS chunk_ids,
           r.confidence     AS confidence,
           r.deontic        AS deontic,
           r.deontic_source AS deontic_source
    ORDER BY r.confidence DESC, s.typed DESC, r.article_id, r.predicate, s.label, o.label
    LIMIT 25
"""


_GENERIC_BRIDGE_NODES = frozenset({
    # These appear in nearly every regulation and link everything to
    # everything. Anchoring a cross-regulation hop on them produces noise,
    # not a meaningful legal connection, so they're excluded from bridge
    # traversal.
    "Entity", "Obligation", "Risk", "LegalBasis", "TechnicalMeasure",
    "OrganisationalMeasure", "RiskAssessment", "TechnicalOrganisationalMeasure",
    "Right", "Purpose", "Notice", "PersonalData", "DataSubject", "Processing",
    "Documentation", "ProcessingOperation", "CorrectiveActions",
    "ProvideInformation",
})


def _bridge_hop(anchor_rows: List[dict]) -> List[dict]:
    """
    Second traversal hop across shared 'bridge' concept nodes.

    A bridge node is a concept that appears in more than one regulation (the
    graph has ~20 meaningful ones, e.g. AutomatedDecision, DemonstrateConformity,
    QualityManagementSystem, mostly ontology-typed). The first hop lands the
    retriever on one regulation's version of a concept; this hop follows the
    shared node into the OTHER regulations that use it.

    Without this, a cross-regulation question (e.g. 'how do GDPR and DUAA
    differ on automated decisions?') finds the GDPR side and stops. This is
    the step that makes the graph actually traversed rather than merely
    looked up.
    """
    if not anchor_rows:
        return []

    # Concept labels the first hop actually landed on, and the regs already covered.
    anchor_labels = list(
        ({r.get("subject") for r in anchor_rows if r.get("subject")}
         | {r.get("object") for r in anchor_rows if r.get("object")})
        - _GENERIC_BRIDGE_NODES)
    seen_regs = list({r.get("regulation") for r in anchor_rows if r.get("regulation")})
    if not anchor_labels:
        return []

    try:
        recs = _store().bridge_hop(anchor_labels, seen_regs)
    except Exception as exc:
        log = _get_log()
        if log:
            log.warning("bridge hop failed (non-fatal): %s", exc)
        return []

    out = []
    for r in recs:
        row = dict(r)
        row["citation"] = _article_id_to_citation(r["article_id"] or "")
        row["bridge"] = True          # tag so the trace / context can mark it
        out.append(row)
    return out


def _diversify_by_article(ranked: List[dict], top_k: int,
                          per_article_cap: int = 4,
                          cross_regulation: bool = False) -> List[dict]:
    """
    Reorders the ranked triples so the top-k spans multiple articles/regulations
    instead of being monopolised by one article's redundant edges.

    Two modes:

    cross_regulation=False (single-reg / abstract questions), gentle:
        Round-robin one triple per ARTICLE per cycle, in rank order. A dominant
        article still gets the most slots (it appears in every cycle) but a
        minority article that ranks lower still gets picked up on cycle 1.
        Preserves strong recall on the primary article.

    cross_regulation=True (router emitted concepts spanning >1 regulation),
    strict: round-robin one triple per REGULATION per cycle first, so every
        regulation named in the question is guaranteed a slot before any
        regulation gets a second. This is what forces EU AI Act Art 10 into the
        top-k on a GDPR+AI-Act question, instead of being buried under eleven
        GDPR Art 9 edges.

    Reorders only, never invents. Falls back to rank order to fill any
    remaining slots.
    """
    from collections import defaultdict, OrderedDict

    key = (lambda r: r.get("regulation") or "?") if cross_regulation \
          else (lambda r: r.get("article_id") or "?")

    # bucket triples by the grouping key, preserving rank order within a bucket
    buckets: "OrderedDict[str, list]" = OrderedDict()
    for r in ranked:
        buckets.setdefault(key(r), []).append(r)

    kept: List[dict] = []
    # Round-robin across buckets until top_k is filled or all buckets drained.
    while len(kept) < top_k and any(buckets.values()):
        for k in list(buckets.keys()):
            if buckets[k]:
                kept.append(buckets[k].pop(0))
                if len(kept) >= top_k:
                    break

    # In cross-reg mode, still respect a soft per-article cap WITHIN a
    # regulation so one article of a reg doesn't dominate that reg's share.
    if cross_regulation and per_article_cap:
        capped, seen = [], defaultdict(int)
        overflow = []
        for r in kept:
            a = r.get("article_id") or "?"
            if seen[a] < per_article_cap:
                capped.append(r); seen[a] += 1
            else:
                overflow.append(r)
        for r in overflow:
            if len(capped) >= top_k:
                break
            capped.append(r)
        kept = capped[:top_k]

    return kept[:top_k]


_REF_PREFIX_TO_REG = {
    "GDPR":  "GDPR",
    "EUAI":  "EU AI Act",
    "EUMDR": "EU MDR 2017/745",
    "UKMDR": "UK MDR 2002",
    "DUAA":  "DUAA 2025",
}

def _article_refs_to_kg_ids(refs: list) -> list:
    """
    Maps router article_refs ("EUAI:9", "GDPR:22", "EUAI:AnnexIII") to the KG's
    article_id form ("EU AI Act__Art9"). Solution E: lets a multi-article
    question anchor on the articles it names, instead of hoping keywords hit
    each of Articles 9-15 individually.
    """
    out = []
    for ref in refs or []:
        if ":" not in ref:
            continue
        pfx, art = ref.split(":", 1)
        reg = _REF_PREFIX_TO_REG.get(pfx.upper())
        if not reg:
            continue
        art = art.strip()
        # normalise "AnnexIII" -> "Annex III", "S80-22B" stays, plain "9" -> "9"
        if art.lower().startswith("annex"):
            art = "Annex " + art[5:].strip()
        # DUAA new automated-decision articles are stored as S80-22A..D
        if reg == "DUAA 2025" and art.upper() in ("22A", "22B", "22C", "22D"):
            art = "S80-" + art.upper()
        out.append(f"{reg}__Art{art}")
    return out


_BY_ARTICLE_CYPHER = """
    UNWIND $article_ids AS aid
    MATCH (s:Concept)-[r:REL {article_id: aid}]->(o:Concept)
    RETURN s.label          AS subject,
           s.uri            AS subject_uri,
           s.typed          AS subject_typed,
           o.typed          AS object_typed,
           s.typed          AS typed,
           r.predicate      AS predicate,
           o.label          AS object,
           o.uri            AS object_uri,
           r.regulation     AS regulation,
           r.article_id     AS article_id,
           r.canonical_id   AS canonical_id,
           r.chunk_ids      AS chunk_ids,
           r.confidence     AS confidence,
           r.deontic        AS deontic,
           r.deontic_source AS deontic_source
    ORDER BY r.confidence DESC, s.typed DESC, r.article_id, r.predicate, s.label, o.label
"""


def _fetch_by_article(refs: list) -> List[dict]:
    """Solution E: direct article-anchored retrieval for named provisions."""
    kg_ids = _article_refs_to_kg_ids(refs)
    if not kg_ids:
        return []
    try:
        recs = _store().fetch_by_article(kg_ids)
    except Exception as exc:
        log = _get_log()
        if log:
            log.warning("article-anchored fetch failed (non-fatal): %s", exc)
        return []
    out = []
    for r in recs:
        row = dict(r)
        row["citation"] = _article_id_to_citation(r["article_id"] or "")
        row["by_article"] = True
        out.append(row)
    return out


def kg_retrieve(payload: QueryPayload, top_k: int = 12,
                bridge: bool = True) -> List[dict]:
    """
    Phase 3 KG retrieval, queries the Phase 2 AuraDB schema:
      Node  :Concept  { label, uri, typed, source_reg }
      Edge  :REL      { predicate, predicate_uri, regulation,
                        article_id, chunk_ids, confidence }

    Strategy:
      1. Build keyword list from data_type + system_type + topic
      2. Match :Concept nodes whose label OR uri contains any keyword
      3. Traverse all :REL edges from those anchor nodes
      4. Prefer typed=true nodes (ontology-grounded) via ORDER BY
      5. Return structured rows the LLM can cite directly
    """
    # 1. Build keyword list
    # keyword_sources = [
    #     payload.data_type,
    #     payload.system_type,
    #     payload.topic,
    # ]
    # keywords = list({
    #     _kg_keyword(src)
    #     for src in keyword_sources
    #     if src  # skip None
    # })
    # if not keywords:
    #     return []
    # Concepts (from the router) are the primary anchor for cross-regulation
    # and abstract questions, they carry the substantive legal terms the
    # graph is indexed by. topic/data_type/etc. are kept as a fallback for
    # older router outputs that predate the `concepts` field.
    concept_list = getattr(payload, "concepts", None) or []
    keywords = _kg_keywords(
        *concept_list,
        payload.data_type,
        payload.system_type,
        payload.topic,
        payload.purpose,
        payload.action,
    )
    if not keywords:
        return []

    # 2 + 3. Anchor on keyword, traverse :REL, via the breaker-wrapped store.
    # (Cypher text now lives in graph_store._MATCH_CYPHER; kept in sync there.
    # Two passes in one query: Pass A anchor-is-subject, Pass B anchor-is-object,
    # so both "HealthData --hasLegalBasis--> Consent" and
    # "Processing --appliesTo--> HealthData" patterns are caught.)
    try:
        recs = _store().match_by_keywords(keywords)
    except Exception as exc:
        # Never hard-fail, RAG still runs if KG is unavailable.
        log = _get_log()
        if log:
            log.warning("kg_retrieve failed: %s", exc)
        return []

    # 4. Deduplicate + format
    seen, results = set(), []
    for r in recs:
        key = f"{r['subject']}|{r['predicate']}|{r['object']}"
        if key in seen:
            continue
        seen.add(key)
        row = dict(r)
        # Add human-readable citation so build_context and the LLM can cite it
        row["citation"] = _article_id_to_citation(r["article_id"] or "")
        results.append(row)

    # Loud, once: a graph loaded by p2_step5 v1 has no deontic property.
    # Silently scoring deontic as None across every arm is the failure mode
    # this guard exists to prevent.
    if results and not any(r.get("deontic") for r in results):
        log = _get_log()
        if log:
            log.warning(
                "KG edges carry no `deontic` property — the graph was loaded by "
                "p2_step5 v1. Re-run `python p2_step5_aura_graph.py` before "
                "evaluating, or deontic_align will be null for every arm."
            )

    # Did the router name explicit articles? If so, the question has declared
    # its own scope, and we must NOT wander outside it (no bridge into other
    # regulations, no cross-reg round-robin that evicts the named articles).
    refs = getattr(payload, "article_refs", None)
    ref_kg_ids = set(_article_refs_to_kg_ids(refs)) if refs else set()
    ref_regs = {rid.split("__")[0] for rid in ref_kg_ids}
    scoped_single_reg = bool(ref_regs) and len(ref_regs) == 1

    # 4b. Bridge hop, follows shared concept nodes into OTHER regulations.
    # Suppressed when the question named explicit articles: their scope is
    # fixed, and bridging would drag in regulations the question didn't ask for.
    if bridge and results and not refs:
        seen_keys = {f"{r.get('subject')}|{r.get('predicate')}|{r.get('object')}"
                     for r in results}
        for br in _bridge_hop(results):
            key = f"{br.get('subject')}|{br.get('predicate')}|{br.get('object')}"
            if key not in seen_keys:
                seen_keys.add(key)
                results.append(br)

    # 4c. Solution E, article-anchored retrieval. When the router captured
    # explicit article references (e.g. "Articles 9 to 15"), fetch those
    # articles directly rather than relying on keyword matches to reach each
    # one. These are prepended so the diversity step treats them as first-class.
    if refs:
        seen_keys = {f"{r.get('subject')}|{r.get('predicate')}|{r.get('object')}"
                     for r in results}
        by_art = _fetch_by_article(refs)
        prepend = []
        for r in by_art:
            key = f"{r.get('subject')}|{r.get('predicate')}|{r.get('object')}"
            if key not in seen_keys:
                seen_keys.add(key)
                prepend.append(r)
        results = prepend + results

        # If every named article is from ONE regulation, this is a scoped
        # single-regulation question (e.g. B25 "EU AI Act Articles 9-15").
        # Restrict to that regulation so keyword-matched noise from other
        # regulations cannot evict the named articles.
        if scoped_single_reg:
            keep_reg = next(iter(ref_regs))
            results = [r for r in results
                       if (r.get("article_id") or "").split("__")[0] == keep_reg]

    # 5. Rank, then apply article-diversity so no single article monopolises
    #    the top-k. Ten near-identical triples from one article are one fact
    #    and were starving other articles.
    #
    #    Mode selection:
    #    - Named articles from ONE regulation  -> article-level round-robin,
    #      so all the named articles share the budget (B25 keeps all of 9-15).
    #    - Retrieved triples span >1 regulation AND no single-reg scope ->
    #      regulation-level round-robin (the cross-regulation case, e.g. C34).
    #    - Otherwise -> gentle article-level round-robin.
    results = _rank_triples(results, keywords)
    if top_k:
        regs_present = {r.get("regulation") for r in results if r.get("regulation")}
        cross = (len(regs_present) > 1) and not scoped_single_reg
        results = _diversify_by_article(results, top_k, per_article_cap=4,
                                        cross_regulation=cross)
    return results


def _get_log():
    """Return a logger without a module-level import dependency."""
    try:
        import logging
        return logging.getLogger(__name__)
    except Exception:
        return None


# Retrieval: Vector Store
def rag_retrieve(payload: QueryPayload, k: int = 4) -> List[dict]:
    """Multi-angle RAG retrieval covering GDPR, EU AI Act, MDR, and DUAA 2025.

    Query construction rules:
    - Base queries anchor on the specific compliance action (store/share/deploy),
      NOT on generic data type strings, this stops Art16/Art18 (data subject
      rights) from crowding out Art6/Art9 (lawful basis) for storage questions.
    - Purpose-driven queries fire the exact legal path (Art9(2)(j) for training,
      Art9(2)(h) for direct care, DUAA s.80 for significant automated decisions).
    - Deployment context queries add sector-specific obligations.
    - Legal term expansion bridges user vocabulary to regulatory text.
    """
    col = _collection()
    dt   = payload.data_type          or "personal data"
    st   = payload.system_type        or "AI system"
    act  = payload.action             or "process"
    purp = payload.purpose            or ""
    ctx  = payload.deployment_context or ""
    jur  = payload.jurisdiction       or ""

    # Base queries, action-specific, avoids data-subject-rights articles.
    # "store" / "share" -> lawful basis + special category, not erasure/rectification
    base_queries = [
        f"{dt} {act} lawful basis legal basis",
        f"{dt} special category explicit consent Article 9",
        f"{st} high-risk AI obligations Article 6 Annex III",
        f"{dt} {act} controller processor obligations",
    ]

    # Purpose-driven queries
    purpose_queries = []
    if purp:
        purpose_queries.append(f"{dt} {purp} lawful basis GDPR Article 9")
        if "training" in purp.lower() or "research" in purp.lower():
            purpose_queries.append(
                "health data AI model training research statistical purpose "
                "Article 9(2)(j) scientific research exemption"
            )
        if "care" in purp.lower() or "clinical" in purp.lower():
            purpose_queries.append(
                "health data direct patient care clinical decision support "
                "Article 9(2)(h) healthcare professional"
            )
        if "workplace" in purp.lower() or "monitoring" in purp.lower():
            purpose_queries.append(
                "emotion recognition workplace prohibited AI practices Article 5"
            )
        if "hiring" in purp.lower() or "screening" in purp.lower():
            purpose_queries.append(
                "automated CV scoring employment high-risk AI Annex III Article 22"
            )
        if "loan" in purp.lower() or "credit" in purp.lower():
            purpose_queries.append(
                "automated credit loan decision GDPR Article 22 human oversight"
            )
        if "significant" in purp.lower() or "automated" in purp.lower():
            purpose_queries.append(
                "automated significant decision legal effect opt-out "
                "DUAA 2025 Article 22A 22B 22C safeguards human review"
            )

    # Deployment context queries
    context_queries = []
    if ctx:
        if "hospital" in ctx.lower() or "clinical" in ctx.lower():
            context_queries.extend([
                f"medical device software {st} MDR clinical evaluation Article 61",
                f"{st} manufacturer obligations MDR conformity assessment Article 10",
            ])
        if "workplace" in ctx.lower():
            context_queries.append(
                "emotion recognition workplace prohibition EU AI Act Article 5"
            )
        if "public" in ctx.lower():
            context_queries.append(
                "real-time biometric identification public space prohibited Article 5"
            )
        if "financial" in ctx.lower():
            context_queries.append(
                "automated decision loan credit GDPR Article 22 human oversight"
            )
    else:
        # No context, so include MDR as a secondary path, weighted lower
        context_queries.extend([
            f"medical device software {st} MDR Article 2 definition",
            f"{st} clinical evaluation MDR Article 61",
        ])

    # DUAA 2025, fires when jurisdiction is UK or purpose involves automated decisions
    duaa_queries = []
    if "uk" in jur.lower() or "significant" in purp.lower() or "automated" in act.lower():
        duaa_queries.append(
            "automated significant decision DUAA 2025 Article 22A 22B opt-out "
            "human review safeguards Schedule 6"
        )
    if "uk" in jur.lower():
        duaa_queries.append(
            "UK MDR 2002 conformity assessment MHRA Part 4A post-market"
        )

    # Legal term expansions, capped to avoid context overflow
    expansions = (
        _expand_legal_terms(dt)[:3]
        + _expand_legal_terms(st)[:3]
        + _expand_legal_terms(purp)[:2]
    )

    queries = base_queries + purpose_queries + context_queries + duaa_queries + expansions

    # Distances were previously discarded. They're kept now so build_context()
    # can allocate excerpt depth by relevance. The retrieved set is unchanged.
    out, seen = [], {}
    for q in queries:
        res = col.query(query_embeddings=[_embed(q)], n_results=k)
        dists = (res.get("distances") or [[None] * len(res["ids"][0])])[0]
        for cid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], dists
        ):
            if cid in seen:
                prev = seen[cid]["distance"]
                if dist is not None and (prev is None or dist < prev):
                    seen[cid]["distance"] = dist
                continue
            rec = {
                "chunk_id": cid,
                "citation": meta.get("citation", cid),
                "text":     doc,
                "type":     meta.get("type", ""),
                "distance": dist,
            }
            seen[cid] = rec
            out.append(rec)
    return out


def rag_knowledge(payload: QueryPayload, k: int = 6) -> List[dict]:
    """RAG retrieval for knowledge/explanation questions (no permit/deny verdict)."""
    col = _collection()
    q = " ".join(filter(None, [payload.topic, payload.system_type]))
    expansions = _expand_legal_terms(q)
    queries = [
        q or "regulation",
        f"{q} purpose intent recital" if q else "recital purpose intent",
        "technical documentation general description AI system intended purpose",
    ] + expansions[:6]

    out, seen = [], {}
    for query in queries:
        res = col.query(query_embeddings=[_embed(query)], n_results=k)
        dists = (res.get("distances") or [[None] * len(res["ids"][0])])[0]
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                        res["metadatas"][0], dists):
            if cid in seen:
                prev = seen[cid]["distance"]
                if dist is not None and (prev is None or dist < prev):
                    seen[cid]["distance"] = dist
                continue
            rec = {"chunk_id": cid,
                   "citation": meta.get("citation", cid),
                   "text": doc,
                   "type": meta.get("type", ""),
                   "distance": dist}
            seen[cid] = rec
            out.append(rec)
    return out


def _rag_retrieve_combined(payloads: list[QueryPayload], k: int = 3) -> list[dict]:
    """Merge RAG results across all session compliance payloads.
    Used for summary requests, gives the LLM context covering the whole
    session. k is smaller per payload to prevent context overflow."""
    out, seen = [], set()
    for p in payloads:
        chunks = rag_knowledge(p, k=k) if p.intent == "knowledge" else rag_retrieve(p, k=k)
        for c in chunks:
            if c["chunk_id"] not in seen:
                seen.add(c["chunk_id"])
                out.append(c)
    return out


# Context builder
def build_context(kg: List[dict], rag: List[dict]) -> str:
    """
    Merges KG structured rules + RAG excerpts into one context block.

    Phase 3 KG row shape (Phase 2 schema):
      subject, subject_uri, typed, predicate, object, object_uri,
      regulation, article_id, chunk_ids, confidence, citation (added by kg_retrieve)
    """
    lines = ["## STRUCTURED RULES (knowledge graph)"]
    if kg:
        for r in kg:
            subj    = r.get("subject",   "?")
            pred    = r.get("predicate", "?")
            obj     = r.get("object",    "?")
            cite    = r.get("citation",  "")   # human-readable, e.g. "GDPR, Article 6"
            chunks  = r.get("chunk_ids") or []
            typed   = r.get("typed",     False)

            # First two source chunk IDs give the evaluator a trace back to raw text
            chunk_ref = f" [chunks: {', '.join(chunks[:2])}]" if chunks else ""
            typed_tag = "" if typed else " ⚠ untyped"

            deon     = r.get("deontic")
            deon_tag = f" [{deon}]" if deon else ""

            lines.append(
                f"- {subj} --[{pred}]--> {obj}{deon_tag}"
                f"{(' (' + cite + ')') if cite else ''}"
                f"{chunk_ref}{typed_tag}"
            )
    else:
        lines.append("- (no structured rules matched — KG returned 0 results)")

    lines.append("\n## REGULATION EXCERPTS (verbatim, for grounding)")
    # Tiered excerpt depth. Every retrieved chunk is still emitted with its
    # citation header, so the retrieved set, and therefore faithful-F1,
    # hallucination and answerability, is unchanged from the gny_v2 baseline.
    # Only the amount of text per chunk is budgeted, by embedding distance.
    ranked = sorted(
        range(len(rag)),
        key=lambda i: (rag[i].get("distance") is None,
                       rag[i].get("distance") if rag[i].get("distance") is not None else 0.0),
    )
    head = set(ranked[:RAG_HEAD_N])
    for i, c in enumerate(rag):
        limit = RAG_HEAD_CHARS if i in head else RAG_TAIL_CHARS
        raw = c["text"]
        excerpt = raw[:limit].replace("\n", " ")
        # Mark truncation explicitly so the model doesn't treat a cut excerpt
        # as the complete provision when reasoning about it.
        if len(raw) > limit:
            excerpt += " [... excerpt truncated ...]"
        lines.append(f"### {c['citation']}\n{excerpt}")
    return "\n".join(lines)


# LLM system prompts
SYSTEM_VERDICT = """You are a regulatory compliance engine covering GDPR, the EU AI Act,
medical-device regulation (EU MDR 2017/745 and UK MDR 2002), and the
Data (Use and Access) Act 2025 (DUAA 2025).
Decide whether the user's described activity is Allowed, Conditionally Allowed,
Prohibited, or Unclear.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE GATE (check FIRST)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Assess compliance ONLY for: processing personal data, building/deploying AI systems,
placing/using medical devices, and automated significant decisions under the
regulations above.
Unrelated questions → "Unclear", empty rules, explain in reasoning.
Do NOT force a data-protection analysis onto unrelated questions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERPRETING THE PARSED PAYLOAD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The PARSED field contains structured intent extracted from the question. Use it:

purpose - WHY the data/system is used. This determines which GDPR Art.9(2)
exception applies and whether MDR or DUAA applies:
  "direct patient care"              → Art.9(2)(h), MDR likely applies in hospital
  "AI model training"                → Art.9(2)(j) research exemption
  "workplace monitoring"             → EU AI Act Art.5 prohibition may fire
  "loan / credit assessment"         → GDPR Art.22 automated decision rules apply
  "automated significant decision"   → DUAA 2025 s.80 Art.22A-22C safeguards apply

deployment_context - WHERE the system operates:
  "hospital"      → MDR conformity assessment obligations very likely required
  "workplace"     → emotion recognition AI is PROHIBITED under EU AI Act Art.5
  "public space"  → real-time biometric AI is PROHIBITED under EU AI Act Art.5
  "financial services" → GDPR Art.22 automated decisions likely apply
  null/other      → do NOT assume MDR applies without explicit medical context

jurisdiction - WHERE the operator is based:
  "UK"    → UK MDR 2002 applies instead of EU MDR; DUAA 2025 may apply
  "EU"    → EU MDR 2017/745 applies; DUAA does not apply
  "EU+UK" → both MDR regimes may apply; consider DUAA for automated decisions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL DISTINCTION - PROHIBITS IN CONTEXT vs PROHIBITED ACTIVITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The CONTEXT may show rules like "Health Data [PROHIBITS] processing without lawful basis".
This means the REGULATION prohibits processing WITHOUT meeting conditions - NOT that
the activity itself is prohibited. If conditions can be met (consent, legal obligation, etc.),
the verdict is "Conditionally Allowed", not "Prohibited".
Reserve "Prohibited" ONLY for activities explicitly banned regardless of conditions:
  - EU AI Act Art.5: real-time biometric ID in public spaces
  - EU AI Act Art.5: emotion recognition in workplace/education
  - EU AI Act Art.5: social scoring by public authorities
  - EU AI Act Art.5: subliminal manipulation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANALYSIS RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Base answer ONLY on the CONTEXT. Do NOT use outside knowledge.
- STRUCTURED RULES section contains typed triples from the knowledge graph.
  Each rule is formatted as: Subject --[predicate]--> Object (Regulation, Article N)
  Use the article citation in parentheses directly in your "rules" array,
  e.g. "GDPR, Article 9" — do not invent article numbers.
- REGULATION EXCERPTS section contains verbatim regulatory text for grounding.
  Cite the article header shown above each excerpt.
- If context is insufficient → "Unclear".
- Consider EVERY applicable dimension the context supports:
  (1) GDPR — lawful basis, special-category data, automated decisions
  (2) EU AI Act — prohibited practices (Art.5), high-risk classification (Art.6),
      obligations (Arts.9-15), transparency (Art.13)
  (3) MDR — ONLY when deployment_context is "hospital" or system is clearly for
      medical diagnosis/treatment. If jurisdiction="UK" apply UK MDR 2002;
      if "EU" apply EU MDR 2017/745; if "EU+UK" consider both.
  (4) DUAA 2025 — apply when jurisdiction="UK" AND the system makes automated
      decisions with significant effects on individuals (s.80 Art.22A-22C):
      opt-out rights, human review, safeguards, Schedule 6 exemptions.
      Do NOT apply DUAA to EU-only scenarios.
- ⚠ untyped in a STRUCTURED RULE means it was extracted organically — weight
  slightly lower than typed rules.
- Recitals in context explain legislative intent — cite the operative article.
- Do NOT invent scenarios the user did not describe.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONDITIONS (when Conditionally Allowed)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When verdict is "Conditionally Allowed", populate "conditions" with a numbered
list of concrete steps the operator MUST take. Each condition must cite the
article that requires it. Be specific - not "comply with GDPR" but
"Obtain explicit consent from data subjects (GDPR, Art.9(2)(a))".
For all other verdicts, "conditions" must be [].

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIDENCE CALIBRATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
90-100: context directly and fully answers the question across all relevant dimensions
70-85:  context partially covers it, some dimensions missing
50-69:  context is thin or question extends beyond what was provided
<50:    significant gaps, verdict is an estimate

Multi-regulation questions (GDPR + AI Act + MDR + DUAA) rarely exceed 85 unless
all relevant dimensions are fully covered in context. Do NOT default to 80 or 100.

Return STRICT JSON only - no prose, no markdown.
EXACT FIELD TYPES - do not deviate:
  "verdict"    : string - exactly one of the six verdict values
  "rules"      : array of strings - citation strings only, e.g. ["GDPR, Article 9"]
  "reasoning"  : string - ONE paragraph of prose. NEVER a list or array.
  "conditions" : array of strings - specific steps when Conditionally Allowed, else []
  "confidence" : integer - 0 to 100
  "citations"  : array of objects - EVERY provision you relied on, as structured
                 data. One object per provision. Split multi-article citations
                 into separate objects. Use the exact regulation names:
                 "GDPR", "EU AI Act", "EU MDR 2017/745", "UK MDR 2002", "DUAA 2025".
                 UK MDR uses "Regulation N", not "Article N".
                 DUAA uses "Article 22A" / "22B" / "22C" / "22D" / "Schedule 6".

Example shape (values are illustrative only):
{
  "verdict": "Conditionally Allowed",
  "rules": ["GDPR, Article 9", "EU AI Act, Article 6"],
  "reasoning": "The system processes special category health data and must meet strict conditions before deployment.",
  "conditions": ["Obtain explicit consent (GDPR, Art.9(2)(a))", "Conduct DPIA (GDPR, Art.35)"],
  "confidence": <your honest calibration, integer 0-100 — see the scale above; do not copy this example>,
  "citations": [
    {"regulation": "GDPR", "provision": "Article 9"},
    {"regulation": "EU AI Act", "provision": "Article 6"}
  ]
}"""

# Backward-compat alias. api.py and analyze() import `SYSTEM`.
SYSTEM = SYSTEM_VERDICT

SYSTEM_KNOWLEDGE = """You are a regulatory information assistant for GDPR, the EU AI Act,
the MDR (EU MDR 2017/745 and UK MDR 2002), and the Data (Use and Access) Act 2025 (DUAA 2025).
The user is asking you to EXPLAIN or DEFINE a rule or concept -
this is informational, NOT a permit/deny decision.

RULES:
- Answer using ONLY the provided CONTEXT. Do NOT use outside knowledge.
- Cite the specific articles you used in "rules".
- Keep "verdict" exactly "Informational".
- "conditions" must always be [] for knowledge responses.
- If context does not fully cover the question, say so clearly in reasoning,
  explain what IS known, and suggest consulting the official regulation text.
  Set confidence below 60.
- If the user asks for a list, bullet points, or numbered format, structure
  the "reasoning" field accordingly.
- If the user asks for "all", "every", "complete", "full", or "exhaustive"
  requirements, provide a complete structured answer based on all relevant
  CONTEXT excerpts, not just the first matching article.
- Preserve nested legal structure where the CONTEXT contains chapters,
  sections, paragraphs, points, sub-points, or numbered duties. For example,
  if a rule has Article → paragraph → point, keep that hierarchy clear in
  the reasoning.
- When multiple regulations are relevant, group the explanation by regulation
  where possible, for example GDPR first, then EU AI Act, then MDR.
- Context may include recital excerpts - use them to explain legislative intent
  alongside the operative articles.
- Calibrate confidence honestly:
  90-100: context directly and fully answers the question
  70-85:  partially covered
  Below 70: context is thin or question goes beyond what is provided
  Do NOT default to 80 every time.

Return STRICT JSON only - no prose, no markdown.
EXACT FIELD TYPES:
  "verdict"    : string - always exactly "Informational"
  "rules"      : array of strings
  "reasoning"  : string - ONE paragraph or numbered prose. NEVER a list or array.
  "conditions" : array - always [] for knowledge responses
  "confidence" : integer - 0 to 100
  "citations"  : array of objects - EVERY provision you relied on, as structured
                 data. One object per provision. Split multi-article citations
                 into separate objects. Use the exact regulation names:
                 "GDPR", "EU AI Act", "EU MDR 2017/745", "UK MDR 2002", "DUAA 2025".
                 UK MDR uses "Regulation N", not "Article N".
                 DUAA uses "Article 22A" / "22B" / "22C" / "22D" / "Schedule 6".
                 Cite ONLY provisions that appear in the CONTEXT. Never invent one.

Example shape (values are illustrative only — calibrate confidence yourself):
{
  "verdict": "Informational",
  "rules": ["EU AI Act, Article 6"],
  "reasoning": "High-risk AI systems are those listed in Annex III or that serve as safety components.",
  "conditions": [],
  "confidence": <your honest calibration, integer 0-100 — see the scale above; do not copy this example>,
  "citations": [
    {"regulation": "EU AI Act", "provision": "Article 6"},
    {"regulation": "EU AI Act", "provision": "Annex III"}
  ]
}"""

# Appended to system prompt when conversation history is present.
# Tells the LLM to use prior turns for continuity - this is the core of
# why history makes the system smarter, not just stateful.
_SYSTEM_MEMORY_SUFFIX = """

CONVERSATION MEMORY:
You have access to the recent conversation history (user and assistant turns above).
Use it to:
- Connect the current question to earlier turns (e.g. "what does that mean?"
  refers to what you just said - do NOT ask a clarifying question).
- Avoid repeating information already given.
- If the user answers a follow-up question you asked, treat their answer as
  a continuation - do NOT re-ask the same question.
- If the user asks to reformat or list something from your previous answer,
  use YOUR PREVIOUS RESPONSE from history as the source, not just the CONTEXT.
- If the user asks for an example, always include a concrete real-world
  example in your reasoning that relates to the specific topic being discussed,
  not a generic one."""


# Unified LLM call
def _synthesize(
    system: str,
    prompt: str,
    history_msgs: list[dict] | None = None,
) -> Optional[Verdict]:
    """
    Single synthesis function for all intents. Replaces four functions:
    synthesize_verdict / _synthesize_verdict_with_history /
    synthesize_explanation / _synthesize_explanation_with_history.

    history_msgs: prior conversation turns from _build_history_messages().
    When provided, they sit between the system prompt and the current user
    turn so the LLM sees the conversation flow and can use it for continuity.
    """
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    nudge, last = "", ""
    for _ in range(1 + MAX_RETRIES):
        sys_content = system + nudge
        if history_msgs:
            messages = (
                [{"role": "system", "content": sys_content}]
                + history_msgs
                + [{"role": "user", "content": prompt}]
            )
        else:
            messages = [
                {"role": "system", "content": sys_content},
                {"role": "user",   "content": prompt},
            ]
        try:
            resp = _create_with_backoff(
                client,
                model=MODEL, temperature=0,
                reasoning_effort=REASONING_EFFORT,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                response_format={"type": "json_object"},
                messages=messages,
            )
            return Verdict.model_validate_json(resp.choices[0].message.content)
        except (ValidationError, json.JSONDecodeError, KeyError) as err:
            last  = f"{type(err).__name__}: {str(err)[:160]}"
            nudge = ("\n\nPrevious reply rejected: " + last +
                     ". Return ONLY valid JSON matching the schema.")
            time.sleep(RETRY_DELAY)

    print(f"[fail] synthesis failed -> {last}")
    return None


# Canned responses
def _canned_response(payload: QueryPayload) -> Optional[Verdict]:
    """
    Handles all non-retrieval intents in one place.
    Returns a Verdict immediately (no KG/RAG/LLM needed).
    Returns None if the intent requires retrieval (scenario / knowledge).

    This replaces the 7x2 if-blocks that were duplicated across analyze()
    and analyze_with_history(). One source of truth for every canned response.
    """
    match payload.intent:

        case "greeting":
            return Verdict(verdict="Informational", rules=[], confidence=100,
                           reasoning="Hi there! What are you trying to figure out today?")

        case "help":
            return Verdict(
                verdict="Informational", rules=[], confidence=100,
                reasoning=(
                    "Happy to help - what kind of question are you facing? "
                    "Is it about whether a specific system or action is permitted, "
                    "or are you trying to understand what a particular regulation requires?"
                ),
            )

        case "examples":
            return Verdict(
                verdict="Informational", rules=[], confidence=100,
                reasoning=(
                    "Here are some questions you can ask KEP_FALL:\n"
                    "1. Can my elderly-care assistant store fall-risk predictions and share them with caregivers?\n"
                    "2. Does a wearable fall-risk predictor need explicit consent?\n"
                    "3. Is an AI care assistant a high-risk AI system?\n"
                    "4. What human oversight is required for an AI care assistant?\n"
                    "5. Is fall-risk prediction software a medical device?\n"
                    "6. Can health data be used to train a bias-detection model?"
                ),
            )

        case "sensitive":
            return Verdict(
                verdict="Out of Scope", rules=[], confidence=100,
                reasoning=(
                    "I want to make sure you're okay. If you or someone you know "
                    "is in danger or distress, please reach out to emergency services "
                    "or a crisis support line in your country immediately.\n\n"
                    "KEP_FALL is a regulatory compliance tool and cannot help with "
                    "questions involving harm to people. If there is a genuine "
                    "compliance question behind what you are asking - for example, "
                    "about end-of-life care data, AI systems in palliative care, "
                    "or medical device obligations - I am here for that."
                ),
            )

        case "medical_advice":
            return Verdict(
                verdict="Out of Scope", rules=[], confidence=100,
                reasoning=(
                    "That sounds like a personal health question - and for that, "
                    "a qualified healthcare professional is the right person to ask. "
                    "If it's urgent, please contact your local emergency service.\n\n"
                    "If your question is actually about whether an AI system or medical "
                    "device is permitted to handle this kind of information under GDPR, "
                    "the EU AI Act, or MDR - that's exactly what I'm here for. "
                    "Could you tell me a bit more about what you're trying to find out?"
                ),
            )

        case "unsupported_regulation":
            return Verdict(
                verdict="Out of Scope", rules=[], confidence=100,
                reasoning=(
                    "That touches a legal area outside my current scope. "
                    "I cover GDPR, the EU AI Act, EU MDR 2017/745, UK MDR 2002, "
                    "and the Data (Use and Access) Act 2025 (DUAA 2025) — "
                    "which apply across the EU, EEA, and UK. For other "
                    "legal areas, a licensed legal professional would be the right person "
                    "to consult.\n\n"
                    "If there's a data protection, AI system, medical-device, or automated "
                    "decision-making angle to your question, I'm happy to look at that part "
                    "— just let me know."
                ),
            )

        case "clarify":
            jur = getattr(payload, "jurisdiction", None)
            jur_note = ""
            if jur and jur.startswith("other:"):
                country = jur.split(":", 1)[1]
                jur_note = (
                    f" I also noticed you mentioned {country} - KEP_FALL covers EU/EEA "
                    f"and UK regulations, which may still apply depending on where your "
                    f"data subjects are located."
                )
            return Verdict(
                verdict="Informational", rules=[], confidence=100,
                reasoning=(
                    "That could mean a couple of different things. Are you asking about "
                    "a personal situation - for example, what to do in a health or "
                    "medication scenario? Or are you asking whether an AI system, care "
                    "assistant, or medical device is permitted to handle this kind of "
                    "information under GDPR, the EU AI Act, or MDR?" + jur_note
                ),
            )

        case "out_of_scope":
            return Verdict(
                verdict="Out of Scope", rules=[], confidence=100,
                reasoning=(
                    "That one's outside what I'm built for. I focus on healthcare AI "
                    "and medical-device compliance - things like whether a system can "
                    "lawfully process health data, whether an AI system is high-risk, "
                    "or whether software qualifies as a medical device under EU or UK "
                    "regulation.\n\n"
                    "If your question has a data protection, AI, or medical-device "
                    "angle, feel free to rephrase it and I'll do my best. "
                    "Not sure how? Type 'give me examples' and I'll show you."
                ),
            )

        case _:
            return None  # scenario / knowledge -> needs retrieval


# History helpers
def _build_history_messages(history: list[dict]) -> list[dict]:
    """
    Converts SQLite message rows to LLM message dicts.
    These go BETWEEN the system prompt and the current user turn so the LLM
    sees the conversation and can maintain continuity (the whole point of history).

    Note: api.py must store the payload alongside the verdict so
    _extract_last_payload() and _extract_all_payloads() can read it back.
    Add "payload": parsed to verdict_payload in api.py's /query endpoint.
    """
    msgs = []
    for row in history[-_HISTORY_TURNS:]:
        if row["role"] == "user":
            msgs.append({"role": "user", "content": row["content"]})
        else:
            v = row.get("verdict")
            text = (f"[{v['verdict']}] {v['reasoning']}"
                    if v and v.get("reasoning") else row["content"])
            msgs.append({"role": "assistant", "content": text})
    return msgs


def _extract_last_payload(history: list[dict]) -> Optional[QueryPayload]:
    """Returns the most recent compliance payload stored in history.
    Used for vague follow-ups ('explain that'), retrieval uses the
    previous topic rather than trying to retrieve on 'explain that'."""
    for m in reversed(history):
        if m["role"] == "assistant" and m.get("verdict"):
            stored = m["verdict"].get("payload")
            if stored and stored.get("intent") in ("scenario", "knowledge"):
                try:
                    return QueryPayload(**stored)
                except Exception:
                    continue
    return None


def _extract_all_payloads(history: list[dict]) -> list[QueryPayload]:
    """Collects all compliance payloads from the session, used for summary requests."""
    payloads, seen_keys = [], set()
    for m in history:
        if m["role"] == "assistant" and m.get("verdict"):
            stored = m["verdict"].get("payload")
            if stored and stored.get("intent") in ("scenario", "knowledge"):
                key = f"{stored.get('topic','')}|{stored.get('data_type','')}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    try:
                        payloads.append(QueryPayload(**stored))
                    except Exception:
                        continue
    return payloads


# Retrieval routing helpers
_VAGUE_PATTERNS = [
    r"^(explain|clarify|elaborate|describe)\s*(that|this|it|more|further)?\.?$",
    r"^(what does that mean|what do you mean|i don't understand)\.?$",
    r"^(tell me more|give me more|more details|more information)\.?$",
    r"^in simple(r)? terms\.?$",
    r"^in plain (english|language)\.?$",
    r"^(list (that|it|them|those)|put it in a list|list format|in list format)\.?$",
    r"^(the \d+(st|nd|rd|th) one|option \d|choice \d)\.?$",
    r"^(yes|no|okay|ok|sure|go ahead|proceed|continue)\.?$",
    r"^(what about|how about|and (what|how) about)\.?$",
    r"^(can you give (me )?(an? )?(example|more)).*$",
    r"^simply put\.?$",
    r"^(explain this|explain it|explain more)\.?$",
    r"^(make it clearer|make this clearer)\.?$",
    r"^(make it shorter|shorter|summarise that|summarize that)\.?$",
    r"^(put it in points|give it in points|points please)\.?$",
    r"^(give example|give an example|example please)\.?$",
    r"^(why|how so|why is that)\.?$",
]

_SUMMARY_PATTERNS = [
    r".*(summar(y|ise|ize)|overview|recap|wrap up|put it all together).*",
    r".*(everything (we|you) (discussed|covered|talked about)).*",
    r".*(all of (this|that|the above)).*",
    r".*(combine|consolidate|bring it all together).*",
    r".*(all (the )?regulations? (discussed|mentioned|covered)).*",
    r".*(give me an example.*(cover|showing|for all|across all)).*",
    r".*(bullet points?.*(all|everything|summary|overview)).*",
    r".*(list.*(all|everything|summary|overview)).*",
    r".*(show.*(all|everything|summary|overview)).*",
    r".*(what have we discussed).*",
    r".*(what did we cover).*",
]


def _is_vague_followup(question: str) -> bool:
    q = question.strip().lower()
    return any(re.match(p, q) for p in _VAGUE_PATTERNS)


def _is_summary_request(question: str) -> bool:
    q = question.strip().lower()
    return any(re.search(p, q) for p in _SUMMARY_PATTERNS)


def _route(question: str, history: list[dict] | None) -> Optional[QueryPayload]:
    """
    Classifies intent. When history exists, prepends recent context so
    follow-up questions like 'what does that mean?' route correctly instead
    of firing the clarify handler.
    """
    if not history or len(history) < 2:
        return understand_query(question)

    ctx_lines = []
    for m in history[-4:-1]:  # last 2 exchanges, not including current turn
        if m["role"] == "user":
            ctx_lines.append(f"User: {m['content'][:150]}")
        else:
            v = m.get("verdict")
            if v and v.get("reasoning"):
                ctx_lines.append(f"KEP_FALL: [{v['verdict']}] {v['reasoning'][:200]}")
            else:
                ctx_lines.append(f"KEP_FALL: {m['content'][:150]}")

    if not ctx_lines:
        return understand_query(question)

    routed = (
        "[Recent conversation]\n"
        + "\n".join(ctx_lines)
        + "\n[Current question] " + question
    )
    return understand_query(routed)


# Phase 3 — three-stage pipeline: prepare -> retrieve -> synthesize
#
# analyze() used to route, retrieve and synthesize in one monolith, and
# analyze_trace() duplicated the same branching (and had drifted, note the
# stale commented-out knowledge branch in the old version). Splitting the
# pipeline into three composable stages:
#   * removes the duplication (analyze and analyze_trace now share one path)
#   * lets the API route ONCE instead of three times (see api._run_pipeline)
#   * makes retrieved KG/RAG evidence a first-class return value instead of a
#     local that gets discarded, the foundation for the provenance UI and for
#     emitting an `evidence` SSE frame before the verdict is ready
#
# kg_retrieve / rag_retrieve / rag_knowledge / build_context / _synthesize
# are unchanged. The eval harness imports those directly and its numbers are
# frozen; nothing here touches them.

@dataclass
class Plan:
    """Everything the routing stage decided, so retrieval/synthesis needn't
    re-route. `payload` is what the question routed to; `retrieval_payload` is
    what retrieval should actually anchor on (differs only for vague
    follow-ups, which inherit the previous turn's payload)."""
    question:          str
    payload:           QueryPayload
    retrieval_payload: QueryPayload
    intent:            str
    mode:              str                 # "canned" | "summary" | "knowledge" | "scenario"
    canned:            Optional[Verdict] = None
    history_msgs:      list[dict] = field(default_factory=list)
    memory_suffix:     str = ""
    summary_payloads:  list[QueryPayload] = field(default_factory=list)


@dataclass
class Evidence:
    """Retrieved grounding context. This is the bundle that later becomes the
    Trace surfaced to the UI; for now it carries exactly what synthesis needs
    plus the raw kg/rag rows so nothing is thrown away."""
    kg:      List[dict] = field(default_factory=list)
    rag:     List[dict] = field(default_factory=list)
    context: str = ""
    system:  str = ""                      # which system prompt this evidence feeds


def evidence_summary(evidence: Evidence, kg_limit: int = 12,
                     rag_limit: int = 8) -> dict:
    """
    Compact, JSON-safe view of an Evidence bundle for the `evidence` SSE frame
    and the provenance UI. Sends the retrieved graph edges and passage
    citations, NOT the full chunk text (that's rehydrated on demand later).

    Passages are sorted closest-first by vector distance and capped at
    `rag_limit`: the tail of a k-NN search is weak by construction (everything
    has *some* similarity), so showing all of it makes retrieval look noisier
    than it is. `counts.passages` always reports the true retrieved total, so
    the UI can honestly label "showing N of M" rather than hiding the cut.

    This is deliberately a plain dict, not a Pydantic model: it's a wire
    format that the frontend consumes, and keeping it a dict avoids coupling
    the API schema to internal row shapes.
    """
    edges = []
    for r in evidence.kg[:kg_limit]:
        edges.append({
            "subject":    r.get("subject"),
            "predicate":  r.get("predicate"),
            "object":     r.get("object"),
            "regulation": r.get("regulation"),
            "article_id": r.get("article_id"),
            "citation":   r.get("citation"),
            "deontic":    r.get("deontic"),
            "confidence": r.get("confidence"),
            "typed":      bool(r.get("subject_typed")) and bool(r.get("object_typed")),
            "bridge":     bool(r.get("bridge")),
            "by_article": bool(r.get("by_article")),
        })

    # Closest-first; None distances (rare) sort last. Capped for display.
    ranked = sorted(
        evidence.rag,
        key=lambda c: (c.get("distance") is None, c.get("distance") or 0.0),
    )
    passages = []
    for c in ranked[:rag_limit]:
        passages.append({
            "chunk_id":   c.get("chunk_id"),
            "citation":   c.get("citation"),
            "distance":   c.get("distance"),
        })

    regulations = sorted({r.get("regulation") for r in evidence.kg
                          if r.get("regulation")})
    articles = sorted({r.get("article_id") for r in evidence.kg
                       if r.get("article_id")})

    return {
        "edges":    edges,
        "passages": passages,
        "counts": {
            "edges":       len(evidence.kg),
            "passages":    len(evidence.rag),
            "regulations": len(regulations),
            "articles":    len(articles),
        },
        "regulations": regulations,
    }


# Phase 5 — deterministic grounding join
#
# Cross-checks the articles the LLM cited against the articles that were
# actually retrieved, on both channels (graph edges + vector passages). This
# is the runtime twin of the eval's faithful-F1 logic: no LLM involvement,
# pure set membership over canonical article ids.
#
# Every cited article is classified into exactly one of:
#   graph      - backed by a knowledge-graph edge   (strongest: structured)
#   corpus     - backed by a retrieved passage only (grounded in source text)
#   ungrounded - backed by neither (the real red flag: the model reached
#                outside everything it was given)
#
# The three-way split matters: a chat-only interface can't distinguish "the
# model cited a statute it was shown" from "the model cited a statute from
# its parametric memory". This makes that distinction visible and auditable.
import re as _re


def _art_key(canonical: str) -> str:
    """Reduces any canonical id to ARTICLE granularity: REG_ArtNN.

    citation.canonical* produce three subtly different forms
    (GDPR_ArtArticle9 / GDPR_Art9 / GDPR_Art9_Para1). Article-level grounding
    needs them to collapse to one key, and needs sub-paragraph citations
    (Article 9(2)(a)) and DUAA's S80- prefix to match the article-level
    evidence. Everything funnels through here so both sides use identical keys.
    """
    pre, _, rest = canonical.partition("_Art")
    rest = rest.replace("Article", "").replace("article", "")
    rest = rest.split("_")[0].strip()        # drop _Para / _Point suffixes
    rest = _re.sub(r"\(.*", "", rest)         # drop (2)(a) sub-points
    rest = rest.replace("S80-", "")           # DUAA: S80-22C -> 22C
    return f"{pre}_Art{rest}"


def _key_from_kg(article_id: str) -> str:
    return _art_key(_cite.canonical_from_kg(article_id))


def _key_from_chunk(chunk_id: str) -> str:
    return _art_key(_cite.canonical_from_chunk(chunk_id))


def _key_from_citation(regulation: Optional[str], provision: str) -> str:
    return _art_key(_cite.canonical(regulation or "", provision))


def _cited_articles(verdict: Verdict) -> list[dict]:
    """The articles a verdict claims to rely on, each as
    {regulation, provision, key}.

    Prefers the structured `citations` field; falls back to parsing the
    human-readable `rules` strings ("GDPR, Article 9") when the model emitted
    none, mirroring the evaluator's own fallback so live and offline
    grounding agree.
    """
    out, seen = [], set()

    def add(reg, prov):
        if not prov:
            return
        key = _key_from_citation(reg, prov)
        if key in seen:
            return
        seen.add(key)
        out.append({"regulation": reg, "provision": prov, "key": key})

    if verdict.citations:
        for c in verdict.citations:
            add(c.regulation, c.provision)
    else:
        # Fallback: "GDPR, Article 9" -> reg="GDPR", provision="Article 9"
        for rule in (verdict.rules or []):
            reg, sep, prov = rule.partition(",")
            add(reg.strip() if sep else None, (prov or reg).strip())

    return out


def ground_citations(verdict: Verdict, evidence: Evidence) -> dict:
    """
    Classifies every cited article as graph / corpus / ungrounded.

    Returns a JSON-safe dict for the `grounding` SSE frame and the UI badge:

        {
          "items": [ {regulation, provision, status}, ... ],
          "counts": {"graph": n, "corpus": n, "ungrounded": n, "total": n},
          "grounded_ratio": 0.0-1.0,   # (graph+corpus)/total
        }

    An empty citation list yields total=0 and ratio=1.0 (nothing to fault).
    """
    graph_keys  = {_key_from_kg(r.get("article_id"))
                   for r in evidence.kg if r.get("article_id")}
    corpus_keys = {_key_from_chunk(c.get("chunk_id"))
                   for c in evidence.rag if c.get("chunk_id")}

    items = []
    n_graph = n_corpus = n_ungrounded = 0
    for c in _cited_articles(verdict):
        if c["key"] in graph_keys:
            status = "graph"; n_graph += 1
        elif c["key"] in corpus_keys:
            status = "corpus"; n_corpus += 1
        else:
            status = "ungrounded"; n_ungrounded += 1
        items.append({"regulation": c["regulation"],
                      "provision": c["provision"], "status": status})

    total = len(items)
    grounded = n_graph + n_corpus
    return {
        "items": items,
        "counts": {"graph": n_graph, "corpus": n_corpus,
                   "ungrounded": n_ungrounded, "total": total},
        "grounded_ratio": (grounded / total) if total else 1.0,
    }


def reasoning_path(verdict: Verdict, evidence: Evidence,
                   grounding: Optional[dict] = None,
                   max_edges_per_article: int = 2) -> dict:
    """
    Assembles the reasoning path behind a verdict for the provenance diagram.

    This is deliberately not the raw retrieval dump. It starts from the
    articles the verdict actually cited (via ground_citations), and for each
    one attaches the graph edges that carry that article, the real
    subject->predicate->object links the answer rests on. Off-topic retrieved
    edges (device-classification noise, etc.) that no citation relied on are
    excluded, so the diagram shows the path taken, not everything scanned.

    Shape (JSON-safe, for the `reasoning_path` frame / diagram):
        {
          "verdict": "Conditionally Allowed",
          "articles": [
            {
              "regulation": "GDPR", "provision": "Article 6",
              "article_id": "GDPR__Art6", "status": "graph",
              "edges": [{subject, predicate, object, deontic, confidence, typed}, ...]
            }, ...
          ],
          "regulations": ["GDPR", "EU AI Act", ...],  # distinct, in path
          "counts": {"articles": n, "graph": n, "corpus": n, "ungrounded": n}
        }
    """
    grounding = grounding or ground_citations(verdict, evidence)

    # Index retrieved edges by canonical article key, preserving retrieval
    # order (already ranked/diversified upstream).
    edges_by_key: dict[str, list[dict]] = {}
    for r in evidence.kg:
        aid = r.get("article_id")
        if not aid:
            continue
        edges_by_key.setdefault(_key_from_kg(aid), []).append(r)

    articles = []
    regs_seen: list[str] = []
    for item in grounding["items"]:
        key = _key_from_citation(item["regulation"], item["provision"])
        supporting = edges_by_key.get(key, [])[:max_edges_per_article]

        # Regulation label: prefer the edge's, fall back to the citation's.
        reg = (supporting[0].get("regulation") if supporting
               else item.get("regulation")) or item.get("regulation") or "?"
        if reg not in regs_seen:
            regs_seen.append(reg)

        articles.append({
            "regulation": reg,
            "provision":  item["provision"],
            "article_id": (supporting[0].get("article_id") if supporting else None),
            "status":     item["status"],
            "edges": [{
                "subject":    e.get("subject"),
                "predicate":  e.get("predicate"),
                "object":     e.get("object"),
                "deontic":    e.get("deontic"),
                "confidence": e.get("confidence"),
                "typed":      bool(e.get("subject_typed")) and bool(e.get("object_typed")),
            } for e in supporting],
        })

    return {
        "verdict":     verdict.verdict,
        "articles":    articles,
        "regulations": regs_seen,
        "counts":      grounding["counts"],
    }


def prepare(question: str, history: list[dict] | None = None) -> Optional[Plan]:
    """
    Stage 1 - route once, resolve intent, and decide the retrieval strategy.

    Returns None only when routing itself fails (same contract analyze() had).
    A canned intent returns a Plan with mode="canned" and .canned set, so the
    caller can short-circuit without a second routing call.
    """
    payload = _route(question, history)
    if not payload:
        return None

    canned = _canned_response(payload)
    if canned is not None:
        return Plan(question=question, payload=payload,
                    retrieval_payload=payload, intent=payload.intent,
                    mode="canned", canned=canned)

    history_msgs = _build_history_messages(history) if history else []
    memory_suffix = _SYSTEM_MEMORY_SUFFIX if history_msgs else ""

    # Summary: pull context from the entire session, not just this turn.
    if history and _is_summary_request(question):
        all_payloads = _extract_all_payloads(history)
        if all_payloads:
            return Plan(question=question, payload=payload,
                        retrieval_payload=all_payloads[-1],
                        intent=payload.intent, mode="summary",
                        history_msgs=history_msgs, memory_suffix=memory_suffix,
                        summary_payloads=all_payloads)

    # Vague follow-up: inherit the previous payload so retrieval has a real topic.
    retrieval_payload = payload
    if history and _is_vague_followup(question):
        inherited = _extract_last_payload(history)
        if inherited:
            retrieval_payload = inherited

    mode = "knowledge" if payload.intent == "knowledge" else "scenario"
    return Plan(question=question, payload=payload,
                retrieval_payload=retrieval_payload, intent=payload.intent,
                mode=mode, history_msgs=history_msgs, memory_suffix=memory_suffix)


def retrieve(plan: Plan) -> Evidence:
    """
    Stage 2 - fetch grounding context according to the plan's mode.

    Canned plans need no retrieval and return an empty Evidence. Every other
    branch reproduces exactly what analyze() did before, so retrieved content
    is unchanged, only its lifetime is (it's now returned, not discarded).
    """
    if plan.mode == "canned":
        return Evidence()

    if plan.mode == "summary":
        rag = _rag_retrieve_combined(plan.summary_payloads)
        kg  = kg_retrieve(plan.summary_payloads[-1])
        return Evidence(kg=kg, rag=rag,
                        context=build_context(kg, rag), system=SYSTEM)

    if plan.mode == "knowledge":
        kg  = kg_retrieve(plan.retrieval_payload)
        rag = rag_knowledge(plan.retrieval_payload)
        return Evidence(kg=kg, rag=rag,
                        context=build_context(kg, rag), system=SYSTEM_KNOWLEDGE)

    # scenario
    kg  = kg_retrieve(plan.retrieval_payload)
    rag = rag_retrieve(plan.retrieval_payload)
    return Evidence(kg=kg, rag=rag,
                    context=build_context(kg, rag), system=SYSTEM)


def synthesize(plan: Plan, evidence: Evidence) -> Optional[Verdict]:
    """
    Stage 3 - build the prompt and call the LLM.

    Canned plans return their prebuilt verdict without an LLM call. The
    prompt construction below matches the old analyze() per-mode wording
    exactly (knowledge uses TOPIC, scenario/summary use PARSED).
    """
    if plan.mode == "canned":
        return plan.canned

    if plan.mode == "knowledge":
        prompt = (f"QUESTION: {plan.question}\n\n"
                  f"TOPIC: {plan.payload.topic}\n\n"
                  f"CONTEXT:\n{evidence.context}")
    else:  # summary / scenario
        prompt = (f"QUESTION: {plan.question}\n\n"
                  f"PARSED: {plan.payload.model_dump()}\n\n"
                  f"CONTEXT:\n{evidence.context}")

    system = evidence.system + plan.memory_suffix
    return _synthesize(system, prompt, plan.history_msgs or None)


# Public entry points - thin compositions of prepare / retrieve / synthesize.
def analyze(question: str,
            history: list[dict] | None = None) -> Optional[Verdict]:
    """
    Single pipeline entry point.  CLI: analyze(q)   API: analyze(q, history)

    Now a three-line composition. Behaviour is identical to the previous
    monolith for every intent — canned, summary, knowledge, scenario —
    because prepare/retrieve/synthesize reproduce each of those branches
    unchanged.
    """
    plan = prepare(question, history)
    if plan is None:
        return None
    if plan.mode == "canned":
        return plan.canned
    return synthesize(plan, retrieve(plan))


# Backward-compat alias — api.py calls this signature.
def analyze_with_history(question: str, history: list[dict]) -> Optional[Verdict]:
    return analyze(question, history)


def analyze_full(question: str,
                 history: list[dict] | None = None
                 ) -> tuple[Optional[Plan], Optional[Evidence], Optional[Verdict]]:
    """
    Like analyze(), but returns the intermediate stages too:
        (plan, evidence, verdict)

    This is what the API and the provenance UI use when they need the
    retrieved KG/RAG evidence, not just the final verdict. Retrieval runs
    once; the caller gets the verdict AND the grounding it was built from.
    """
    plan = prepare(question, history)
    if plan is None:
        return None, None, None
    if plan.mode == "canned":
        return plan, Evidence(), plan.canned
    evidence = retrieve(plan)
    verdict  = synthesize(plan, evidence)
    return plan, evidence, verdict


def analyze_trace(question: str) -> dict:
    """
    Evaluation-style trace: verdict plus the retrieved KG/RAG context, as a
    plain dict. Single-turn (no history). Kept for any ad-hoc script or
    notebook that used it; the live eval harness builds its own pipeline and
    doesn't call this. Now backed by the shared three-stage path, so it can
    no longer drift from analyze() the way the old duplicated version did.
    """
    trace = {"question": question, "intent": None, "parsed": None,
             "kg": [], "rag": [], "verdict": None, "rules": [],
             "reasoning": "", "confidence": 0}

    plan, evidence, result = analyze_full(question, history=None)
    if plan is None:
        return trace

    trace["intent"] = plan.intent
    trace["parsed"] = plan.payload.model_dump()
    if evidence:
        trace["kg"], trace["rag"] = evidence.kg, evidence.rag
    if result:
        trace.update(verdict=result.verdict, rules=result.rules,
                     reasoning=result.reasoning, confidence=result.confidence)
    return trace




def _print(v: Verdict) -> None:
    print("=" * 60)
    print(f"VERDICT    : {v.verdict}")
    print(f"RULES      : {', '.join(v.rules) if v.rules else '-'}")
    print(f"CONFIDENCE : {v.confidence}%")
    print(f"REASONING  : {v.reasoning}")
    print("=" * 60)


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else (
        "Can my elderly-care assistant store fall-risk predictions "
        "and share them with caregivers?")
    print(f'Q: "{q}"\n')
    result = analyze(q)
    if result:
        _print(result)
    else:
        print("Could not produce a result.")