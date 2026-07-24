"""
phase0_audit.py - Phase 0.4

Runs RETRIEVAL ONLY for every evaluation question using the cached payloads,
and records:

  1. per-section token accounting  (system / KG / RAG / question)
  2. how many chunks RAG actually returns, and which
  3. gold-provision recall of the retrieved set  (the quality baseline that
     Phase 1 must not fall below)
  4. a full dump of every retrieved chunk WITH its embedding distance

No LLM calls. No writes to verdict.py or route.py. Nothing in the live path
is modified - the Chroma collection is wrapped in a recording proxy purely to
capture distances that rag_retrieve currently discards.

The dump written here is what makes Phase 1 free: the sweep over
(chunk cap x truncation) is pure post-processing over retrieval_dump.json,
with no re-embedding and no API calls.

Prereq: python phase0_cache_payloads.py
Run:    python phase0_audit.py
Out:    phase0_out/retrieval_dump.json
        phase0_out/audit_summary.json  + console tables
"""
import json
import os
import statistics
import sys

OUT_DIR = "phase0_out"
PAYLOADS = os.path.join(OUT_DIR, "payloads.json")
QUESTIONS = "eval_questions_full.json"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def count_tokens_factory():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("o200k_base")
        return (lambda t: len(enc.encode(t))), "tiktoken/o200k_base"
    except Exception:
        return (lambda t: len(t) // 4), "approx chars/4"


class RecordingCollection:
    """Transparent proxy around the Chroma collection.

    rag_retrieve() calls col.query() and throws away res["distances"].
    Chroma returns distances by default, so we can capture them here without
    touching verdict.py at all.
    """

    def __init__(self, inner):
        self._inner = inner
        self.log = []

    def query(self, **kwargs):
        res = self._inner.query(**kwargs)
        try:
            self.log.append({
                "ids": res["ids"][0],
                "distances": (res.get("distances") or [[]])[0],
            })
        except Exception:
            pass
        return res

    def __getattr__(self, name):
        return getattr(self._inner, name)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ntok, tok_method = count_tokens_factory()

    if not os.path.exists(PAYLOADS):
        print(f"Missing {PAYLOADS}. Run phase0_cache_payloads.py first.")
        return

    import verdict as V
    from route import QueryPayload
    from citation_norm import canonical_from_chunk

    # Wrap the real collection so distances are captured.
    real_col = V._collection()
    rec = RecordingCollection(real_col)
    V._COLLECTION = rec

    questions = {q["cq_id"]: q for q in
                 json.load(open(QUESTIONS, encoding="utf-8"))}
    payloads = json.load(open(PAYLOADS, encoding="utf-8"))

    sys_verdict_tok = ntok(V.SYSTEM_VERDICT)
    sys_knowledge_tok = ntok(V.SYSTEM_KNOWLEDGE)

    print(f"Token method: {tok_method}")
    print(f"SYSTEM_VERDICT   ~{sys_verdict_tok} tok")
    print(f"SYSTEM_KNOWLEDGE ~{sys_knowledge_tok} tok")
    print(f"Auditing {len(payloads)} cached payloads\n")

    dump = {}
    rows = []

    for n, (cqid, pdict) in enumerate(sorted(payloads.items()), 1):
        cq = questions.get(cqid)
        if cq is None:
            continue
        payload = QueryPayload(**pdict)
        gold = set(cq.get("article_ids", []))

        rec.log.clear()

        kg = V.kg_retrieve(payload, top_k=12)
        if payload.intent == "knowledge":
            rag = V.rag_knowledge(payload)
            sys_tok = sys_knowledge_tok
        else:
            rag = V.rag_retrieve(payload)
            sys_tok = sys_verdict_tok

        # Best (smallest) distance seen for each chunk id across all queries.
        best_dist = {}
        for entry in rec.log:
            for cid, d in zip(entry["ids"], entry["distances"]):
                if cid not in best_dist or d < best_dist[cid]:
                    best_dist[cid] = d

        # Token accounting, mirroring build_context() exactly.
        kg_block = V.build_context(kg, [])
        full_block = V.build_context(kg, rag)
        kg_tok = ntok(kg_block)
        ctx_tok = ntok(full_block)
        rag_tok = ctx_tok - kg_tok
        q_tok = ntok(cq["question"])
        total_in = sys_tok + ctx_tok + q_tok

        # Gold recall of the retrieved chunk set.
        retrieved_ids = {canonical_from_chunk(c["chunk_id"]) for c in rag}
        kg_ids = set()
        for r in kg:
            aid = r.get("article_id")
            if aid:
                try:
                    kg_ids.add(V.canonical_from_kg(aid))
                except Exception:
                    pass
        hit_rag = gold & retrieved_ids
        rec_rag = len(hit_rag) / len(gold) if gold else None

        chunks = []
        for c in rag:
            txt = c.get("text", "")
            chunks.append({
                "chunk_id": c["chunk_id"],
                "canonical": canonical_from_chunk(c["chunk_id"]),
                "citation": c.get("citation", ""),
                "distance": best_dist.get(c["chunk_id"]),
                "chars": len(txt),
                "tokens": ntok(txt[:3000]),
                "is_gold": canonical_from_chunk(c["chunk_id"]) in gold,
                "text": txt,
            })

        dump[cqid] = {
            "question": cq["question"],
            "intent": payload.intent,
            "gold": sorted(gold),
            "n_kg": len(kg),
            "kg_block_tokens": kg_tok,
            "system_tokens": sys_tok,
            "question_tokens": q_tok,
            "chunks": chunks,
        }

        rows.append({
            "cq_id": cqid, "intent": payload.intent,
            "n_rag": len(rag), "n_kg": len(kg),
            "sys_tok": sys_tok, "kg_tok": kg_tok, "rag_tok": rag_tok,
            "total_input_tok": total_in,
            "gold_n": len(gold), "gold_hit": len(hit_rag),
            "recall_rag": rec_rag,
        })

        print(f"[{n}/{len(payloads)}] {cqid:<5} {payload.intent:<9} "
              f"n_rag={len(rag):>3}  rag_tok={rag_tok:>6}  "
              f"total={total_in:>6}  recall="
              f"{'n/a' if rec_rag is None else f'{rec_rag:.2f}'}")

    # Summary
    tot = [r["total_input_tok"] for r in rows]
    ragt = [r["rag_tok"] for r in rows]
    nrag = [r["n_rag"] for r in rows]
    recs = [r["recall_rag"] for r in rows if r["recall_rag"] is not None]

    print("\n" + "=" * 62)
    print("PHASE 0 AUDIT SUMMARY")
    print("=" * 62)
    print(f"questions audited      {len(rows)}")
    print(f"chunks retrieved       mean {statistics.mean(nrag):.1f}  "
          f"median {statistics.median(nrag):.0f}  max {max(nrag)}")
    print(f"RAG block tokens       mean {statistics.mean(ragt):.0f}  "
          f"median {statistics.median(ragt):.0f}  max {max(ragt)}")
    print(f"TOTAL input tokens     mean {statistics.mean(tot):.0f}  "
          f"median {statistics.median(tot):.0f}  max {max(tot)}")
    if recs:
        print(f"gold recall (RAG)      mean {statistics.mean(recs):.3f}  "
              f"perfect on {sum(1 for r in recs if r == 1.0)}/{len(recs)}")

    over8k = sum(1 for t in tot if t > 8000)
    over12k = sum(1 for t in tot if t > 12000)
    print(f"\nfree-tier feasibility (input only, before output tokens)")
    print(f"  exceeds  8,000 TPM (gpt-oss-120b):  {over8k}/{len(tot)}")
    print(f"  exceeds 12,000 TPM (llama-3.3-70b): {over12k}/{len(tot)}")

    with open(os.path.join(OUT_DIR, "retrieval_dump.json"), "w",
              encoding="utf-8") as f:
        json.dump(dump, f, indent=2)
    with open(os.path.join(OUT_DIR, "audit_summary.json"), "w",
              encoding="utf-8") as f:
        json.dump({"token_method": tok_method, "rows": rows}, f, indent=2)

    print(f"\nWritten: {OUT_DIR}/retrieval_dump.json")
    print(f"Written: {OUT_DIR}/audit_summary.json")
    print("\nretrieval_dump.json is the input to the Phase 1 sweep - that "
          "sweep needs no API calls and no re-embedding.")


if __name__ == "__main__":
    main()