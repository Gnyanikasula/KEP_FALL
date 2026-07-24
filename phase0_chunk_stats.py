"""
phase0_chunk_stats.py - Phase 0.3

Profiles the actual Chroma collection so truncation decisions are based on the
documents that are really retrieved, not on regulatory_chunks.json (which holds
559 sub-point chunks, NOT the 55 article-level documents in Chroma).

Read-only. No API calls. No LLM. Does not modify anything.

Run:  python phase0_chunk_stats.py
Out:  phase0_out/chunk_stats.json  + console table
"""
import json
import os
import statistics
import sys

import chromadb

# Mirror verdict.py config exactly.
CHROMA_PATH = "./chroma_db"
COLLECTION = "regulations"
OUT_DIR = "phase0_out"

# Truncation caps to evaluate (chars). 3000 is the current value in
# verdict.py build_context().
CAPS = [800, 1200, 1600, 2000, 2500, 3000, 4000, 6000]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def count_tokens(texts):
    """Token counts via tiktoken if available, else chars/4 approximation.

    gpt-oss uses o200k_harmony; o200k_base is the closest public encoding and
    is within a few percent for English prose. Treat all token numbers here as
    estimates for budgeting, not exact billing figures.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("o200k_base")
        return [len(enc.encode(t)) for t in texts], "tiktoken/o200k_base"
    except Exception:
        return [len(t) // 4 for t in texts], "approx chars/4"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    col = chromadb.PersistentClient(path=CHROMA_PATH).get_collection(COLLECTION)
    res = col.get(include=["documents", "metadatas"])

    ids = res["ids"]
    docs = res["documents"]
    metas = res["metadatas"]

    if not docs:
        print("Collection is empty. Check CHROMA_PATH / COLLECTION.")
        return

    char_lens = [len(d) for d in docs]
    tok_lens, tok_method = count_tokens(docs)

    print(f"\nChroma collection '{COLLECTION}' at {CHROMA_PATH}")
    print(f"Documents: {len(docs)}")
    print(f"Token method: {tok_method}\n")

    print("Document size distribution")
    print(f"  chars   mean {statistics.mean(char_lens):8.0f}   "
          f"median {statistics.median(char_lens):8.0f}   "
          f"min {min(char_lens):6d}   max {max(char_lens):6d}")
    print(f"  tokens  mean {statistics.mean(tok_lens):8.0f}   "
          f"median {statistics.median(tok_lens):8.0f}   "
          f"min {min(tok_lens):6d}   max {max(tok_lens):6d}")

    total_chars = sum(char_lens)
    total_toks = sum(tok_lens)
    print(f"\n  whole corpus: {total_chars:,} chars / ~{total_toks:,} tokens")

    # How much text does each truncation cap actually destroy?
    print("\nTruncation impact (what build_context() would emit per cap)")
    print(f"{'cap':>6} {'docs cut':>9} {'% docs cut':>11} "
          f"{'text kept':>10} {'~tokens/doc':>12}")
    cap_rows = []
    for cap in CAPS:
        cut = sum(1 for c in char_lens if c > cap)
        kept_chars = sum(min(c, cap) for c in char_lens)
        pct_kept = 100.0 * kept_chars / total_chars
        # per-doc token estimate at this cap
        avg_tok_at_cap = (kept_chars / len(docs)) / (total_chars / total_toks)
        cap_rows.append({
            "cap_chars": cap,
            "docs_truncated": cut,
            "pct_docs_truncated": round(100.0 * cut / len(docs), 1),
            "pct_text_retained": round(pct_kept, 1),
            "avg_tokens_per_doc": round(avg_tok_at_cap, 1),
        })
        print(f"{cap:>6} {cut:>9} {100.0*cut/len(docs):>10.1f}% "
              f"{pct_kept:>9.1f}% {avg_tok_at_cap:>12.1f}")

    # Per-regulation breakdown - useful because MDR articles tend to be long
    # and are the ones most at risk from aggressive truncation.
    by_source = {}
    for m, c, t in zip(metas, char_lens, tok_lens):
        src = (m or {}).get("source", "UNKNOWN")
        by_source.setdefault(src, []).append((c, t))

    print("\nBy regulation")
    print(f"{'source':<22} {'n':>4} {'mean chars':>11} {'max chars':>10} {'>3000':>7}")
    src_rows = []
    for src, vals in sorted(by_source.items()):
        cs = [v[0] for v in vals]
        over = sum(1 for c in cs if c > 3000)
        src_rows.append({
            "source": src, "n": len(cs),
            "mean_chars": round(statistics.mean(cs)),
            "max_chars": max(cs), "over_3000": over,
        })
        print(f"{src:<22} {len(cs):>4} {statistics.mean(cs):>11.0f} "
              f"{max(cs):>10} {over:>7}")

    # The 10 largest documents - these dominate any prompt they land in.
    largest = sorted(zip(ids, char_lens, tok_lens, metas),
                     key=lambda x: -x[1])[:10]
    print("\n10 largest documents (these dominate prompt cost when retrieved)")
    for cid, c, t, m in largest:
        cite = (m or {}).get("citation", cid)[:58]
        print(f"  {c:>7} chars  ~{t:>6} tok   {cite}")

    out = {
        "collection": COLLECTION,
        "n_documents": len(docs),
        "token_method": tok_method,
        "chars": {"mean": statistics.mean(char_lens),
                  "median": statistics.median(char_lens),
                  "min": min(char_lens), "max": max(char_lens),
                  "total": total_chars},
        "tokens": {"mean": statistics.mean(tok_lens),
                   "median": statistics.median(tok_lens),
                   "min": min(tok_lens), "max": max(tok_lens),
                   "total": total_toks},
        "truncation_caps": cap_rows,
        "by_source": src_rows,
        "largest": [{"chunk_id": c, "chars": ch, "tokens": tk,
                     "citation": (m or {}).get("citation", "")}
                    for c, ch, tk, m in largest],
    }
    path = os.path.join(OUT_DIR, "chunk_stats.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nWritten: {path}")


if __name__ == "__main__":
    main()