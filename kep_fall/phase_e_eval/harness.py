"""
eval_p5.py — KEP_FALL Phase 5 evaluation harness. FINAL / FROZEN.

Design commitments (don't change these mid-thesis): one canonical article id
everywhere (citation_norm), no prose regex on the primary path; ablation
arms live in a registry, adding one is a single dict entry; every metric is
defined so a perfect retriever scores 1.0 and a degenerate one doesn't
(kg_hit_rate failed this and is gone); every headline claim gets a paired
bootstrap CI, seeded and reproducible.

Metrics:
  citation_f1     P/R/F1 over canonical article ids vs gold.
  answerability   Does the KG return a triple on the gold article? Replaces
                  kg_hit_rate, which asked "did Cypher return any row" and
                  saturated at 1.000, a metric with no discriminative power.
  hallucination   Fraction of cited articles that appear in no retrieved
                  context. A cited article the retriever never surfaced was
                  invented.
  concept_cov     Embedding cosine, not substring. "lawful basis" is close
                  to "legal basis"; the old lexical scorer gave those 0.
  deontic_align   Reads r.deontic off the KG edge, so kg_only is scorable.
  regulation_f1   Scenario questions only: did we name the right statutes?
                  Article F1 is the wrong instrument for "which laws apply".

Usage:
  python eval_p5.py                       # all arms, all questions
  python eval_p5.py --arms hybrid kg_only rag_only
  python eval_p5.py --groups A B --reset
"""

import argparse
import json
import random
import re
import time
from pathlib import Path
from statistics import mean

from sentence_transformers import SentenceTransformer

from kep_fall.phase_d_engine.router import understand_query
from kep_fall.phase_d_engine.engine import (kg_retrieve, rag_retrieve, rag_knowledge,
                     build_context, _synthesize,
                     SYSTEM_KNOWLEDGE, SYSTEM_VERDICT)
from kep_fall.citation import canonical_from_kg, canonical_from_chunk, extract_from_prose
from kep_fall import config

# CQ_PATH   = Path("eval_questions_full.json")
# GOLD_PATH = Path("gold_standard_full.json")
# OUT_DIR   = Path("Results"); OUT_DIR.mkdir(exist_ok=True)
CKPT      = config.ABLATION_CHECKPOINT
CQ_PATH   = config.COMPETENCY_QUESTIONS
GOLD_PATH = config.GOLD_STANDARD
OUT_DIR   = config.EVAL_RESULTS_DIR

RATE_DELAY  = 2.5
CONCEPT_SIM = 0.60
N_BOOTSTRAP = 5000
SEED        = 20260710

_embedder = None
def embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5",
                                        trust_remote_code=True)
    return _embedder


# Ablation registry

def _run(payload, question, use_kg, use_rag, typed_only=None,
         conf_min=None, strip_provenance=False, top_k=12):
    kg = []
    if use_kg:
        kg = kg_retrieve(payload, top_k=top_k)
        if typed_only is True:
            kg = [t for t in kg if t.get("subject_typed") and t.get("object_typed")]
        elif typed_only is False:
            kg = [t for t in kg if not (t.get("subject_typed") and t.get("object_typed"))]
        if conf_min is not None:
            kg = [t for t in kg if t.get("confidence", 0) >= conf_min]
        if strip_provenance:
            kg = [{**t, "article_id": None, "chunk_ids": []} for t in kg]

    rag = []
    if use_rag:
        rag = (rag_knowledge if payload.intent == "knowledge" else rag_retrieve)(payload)

    system = SYSTEM_KNOWLEDGE if payload.intent == "knowledge" else SYSTEM_VERDICT
    prompt = f"QUESTION: {question}\n\nCONTEXT:\n{build_context(kg, rag)}"
    return {"kg": kg, "rag": rag, "verdict": _synthesize(system, prompt)}


ARMS = {
    # retrieval ablation — the headline result
    "hybrid":                dict(use_kg=True,  use_rag=True),
    "kg_only":               dict(use_kg=True,  use_rag=False),
    "rag_only":              dict(use_kg=False, use_rag=True),
    # ontology ablation — does OWL typing earn its place?
    "kg_typed_only":         dict(use_kg=True,  use_rag=False, typed_only=True),
    "kg_untyped_only":       dict(use_kg=True,  use_rag=False, typed_only=False),
    # provenance ablation — citations, or concepts?
    "hybrid_no_provenance":  dict(use_kg=True,  use_rag=True, strip_provenance=True),
    # context-size sweep. The v1 retriever returned up to 50 unranked triples.
    # This is a hyperparameter nobody chose; make it visible rather than tuned.
    "hybrid_topk4":          dict(use_kg=True,  use_rag=True, top_k=4),
    "hybrid_topk24":         dict(use_kg=True,  use_rag=True, top_k=24),
    "hybrid_topk_all":       dict(use_kg=True,  use_rag=True, top_k=0),
    # confidence sweep
    "hybrid_conf50":         dict(use_kg=True,  use_rag=True, conf_min=0.50),
    "hybrid_conf70":         dict(use_kg=True,  use_rag=True, conf_min=0.70),
    "hybrid_conf90":         dict(use_kg=True,  use_rag=True, conf_min=0.90),
}


# helpers

def _kg_articles(trace) -> set:
    return {canonical_from_kg(t.get("article_id") or "")
            for t in trace["kg"] if t.get("article_id")}

def _rag_articles(trace) -> set:
    return {canonical_from_chunk(c.get("chunk_id") or "")
            for c in trace["rag"] if c.get("chunk_id")}

def _answer_text(v) -> str:
    if v is None:
        return ""
    return ((v.reasoning or "") + " " + " ".join(v.rules or [])).strip()


def _predicted(trace, cq) -> set:
    """Structured citations preferred; prose regex is the fallback."""
    v = trace["verdict"]
    if v is None:
        return set()
    cites = getattr(v, "citations", None) or []
    if cites:
        out = set()
        for c in cites:
            reg = getattr(c, "regulation", None) or cq["regulation"]
            prov = getattr(c, "provision", None) or ""
            out |= extract_from_prose(prov, reg) or set()
        if out:
            return out
    return extract_from_prose(_answer_text(v), cq["regulation"])


# scorers

def _prf(exp: set, found: set) -> tuple:
    tp = len(exp & found)
    p  = tp / len(found) if found else 0.0
    r  = tp / len(exp)   if exp   else 1.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f1


def score_citation(trace, cq) -> dict:
    """
    Two figures.

    `f1`           — the naive one. Counts a citation if it matches gold,
                     regardless of whether the system retrieved the evidence.
                     This rewards the LLM's parametric memory of the GDPR:
                     kg_only scored 1.00 on A08/A12/F60 while citing articles
                     none of its 12 retrieved triples mention.

    `faithful_f1`  — counts a citation ONLY if that article appears in the
                     retrieved context. An article the retriever never surfaced
                     was recalled, not retrieved, and the system deserves no
                     credit for it. THIS IS THE HEADLINE NUMBER.

    faithful_f1 == f1 exactly when hallucination == 0.
    """
    exp    = set(cq["article_ids"])
    found  = _predicted(trace, cq)
    if not exp:
        return dict(precision=1.0, recall=1.0, f1=1.0,
                    faithful_precision=1.0, faithful_recall=1.0, faithful_f1=1.0,
                    expected=[], found=[], found_grounded=[])

    retrieved = _kg_articles(trace) | _rag_articles(trace)
    grounded  = found & retrieved

    p,  r,  f1  = _prf(exp, found)
    fp, fr, ff1 = _prf(exp, grounded)
    return dict(precision=p, recall=r, f1=f1,
                faithful_precision=fp, faithful_recall=fr, faithful_f1=ff1,
                expected=sorted(exp), found=sorted(found),
                found_grounded=sorted(grounded))


def score_answerability(trace, cq, uses_kg: bool):
    """
    Is the GOLD article reachable by graph traversal? Not 'did Cypher return a row'.

    Returns None for arms that never query the graph. Reporting rag_only as
    answerability = 0.000 implies it failed a test it never sat.
    """
    if not uses_kg:
        return None
    if not trace["kg"]:
        return 0.0                      # KG was queried and surfaced nothing
    return 1.0 if (set(cq["article_ids"]) & _kg_articles(trace)) else 0.0


def score_hallucination(trace, cq) -> float:
    cited = _predicted(trace, cq)
    if not cited:
        return 0.0
    grounded = _kg_articles(trace) | _rag_articles(trace)
    return len(cited - grounded) / len(cited)


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

def _readable_concept(c: str) -> str:
    """
    'LawfulnessFairnessTransparency' -> 'lawfulness fairness transparency'

    key_concepts are PascalCase ontology labels. Embedding them raw produces a
    near-meaningless vector: the tokenizer sees one rare subword salad, not the
    three legal concepts. This is why A01 cited GDPR Art. 6 perfectly and still
    scored concept_cov = 0.00.
    """
    return _CAMEL.sub(" ", c).replace("_", " ").strip().lower()


def score_concepts(trace, cq) -> float:
    """
    Embedding cosine, not substring.

    Two corrections over v1:
      1. PascalCase concepts are split into words before encoding.
      2. nomic-embed-text-v1.5 REQUIRES task prefixes. verdict.py::_embed
         applies 'search_query: '; this scorer did not, so every concept
         vector was off-distribution. Concepts are queries, answer sentences
         are documents.
    """
    concepts = [_readable_concept(c) for c in cq["key_concepts"].split(";") if c.strip()]
    if not concepts:
        return 1.0
    answer = _answer_text(trace["verdict"])
    if not answer:
        return 0.0
    sents = [s for s in re.split(r"(?<=[.!?])\s+", answer) if len(s) > 10] or [answer]

    m = embedder()
    c_emb = m.encode([f"search_query: {c}"    for c in concepts], normalize_embeddings=True)
    s_emb = m.encode([f"search_document: {s}" for s in sents],    normalize_embeddings=True)
    return float(((c_emb @ s_emb.T).max(axis=1) >= CONCEPT_SIM).mean())


def concept_similarity_dump(trace, cq):
    """--calibrate: raw max-cosine per concept, so CONCEPT_SIM is chosen, not guessed."""
    concepts = [_readable_concept(c) for c in cq["key_concepts"].split(";") if c.strip()]
    answer = _answer_text(trace["verdict"])
    if not concepts or not answer:
        return []
    sents = [s for s in re.split(r"(?<=[.!?])\s+", answer) if len(s) > 10] or [answer]
    m = embedder()
    c_emb = m.encode([f"search_query: {c}"    for c in concepts], normalize_embeddings=True)
    s_emb = m.encode([f"search_document: {s}" for s in sents],    normalize_embeddings=True)
    sims = (c_emb @ s_emb.T).max(axis=1)
    return list(zip(concepts, [float(x) for x in sims]))


DEONTIC_CUES = {
    "obligation":          {"must", "shall", "required", "obligation", "duty"},
    "prohibition":         {"prohibited", "forbidden", "must not", "shall not",
                            "may not", "no person shall", "banned"},
    "permission":          {"may", "permitted", "allowed", "exception", "exemption",
                            "empowered", "right to"},
    "classification_rule": {"classified", "classification", "class", "category",
                            "qualifies", "defined as", "means"},
    "amendment":           {"amend", "amendment", "substitute", "consequential",
                            "inserted"},
}

def score_deontic(trace, gold, cq):
    """Scorable for kg_only because r.deontic now lives on the edge."""
    answer = _answer_text(trace["verdict"]).lower()
    if not answer:
        return None
    types = {t["deontic"] for t in trace["kg"] if t.get("deontic")}
    if not types:
        types = {gold[a]["deontic_type"] for a in _rag_articles(trace) if a in gold}
    if not types:
        return None
    hits = sum(1 for t in types
               if any(cue in answer for cue in DEONTIC_CUES.get(t, ())))
    return hits / len(types)


REG_PATTERNS = {
    "GDPR":            r"\bGDPR\b",
    "EU AI Act":       r"\bAI Act\b|\bEU AI Act\b",
    "EU MDR 2017/745": r"\bEU MDR\b|\bMDR\b|2017/745",
    "UK MDR 2002":     r"\bUK MDR\b",
    "DUAA 2025":       r"\bDUAA\b|Data \(Use and Access\)",
}

def score_regulation_set(trace, cq):
    """Scenario questions: 'which laws apply'. Rewards correct EXCLUSION too."""
    exp = set(cq.get("expected_regulations") or [])
    if not exp:
        return None
    answer = _answer_text(trace["verdict"])
    found = {r for r, pat in REG_PATTERNS.items()
             if re.search(pat, answer, re.I)}
    tp = len(exp & found)
    p  = tp / len(found) if found else 0.0
    r  = tp / len(exp)
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return dict(precision=p, recall=r, f1=f1,
                expected=sorted(exp), found=sorted(found))


# paired bootstrap

def bootstrap_ci(a, b, n=N_BOOTSTRAP, seed=SEED):
    """
    Arms are evaluated on the SAME questions, so the deltas are paired.
    Resample questions, not scores. Returns (mean_delta, lo95, hi95, p).
    """
    rng = random.Random(seed)
    deltas = [x - y for x, y in zip(a, b)]
    k = len(deltas)
    boots = sorted(mean([deltas[rng.randrange(k)] for _ in range(k)])
                   for _ in range(n))
    lo, hi = boots[int(.025 * n)], boots[int(.975 * n)]
    p = 2 * min(sum(x <= 0 for x in boots), sum(x >= 0 for x in boots)) / n
    return mean(deltas), lo, hi, min(p, 1.0)


# main

def main(arms=None, groups=None):
    cqs = json.load(open(CQ_PATH, encoding="utf-8"))
    if groups:
        cqs = [c for c in cqs if c["group"] in groups]

    gold = {a["article_id"]: a
            for a in json.load(open(GOLD_PATH, encoding="utf-8"))["annotations"]}

    # Fail loudly rather than silently scoring 0 on an unanswerable question.
    orphans = {a for c in cqs for a in c["article_ids"] if a not in gold}
    if orphans:
        raise SystemExit(f"article_ids with no gold annotation: {sorted(orphans)}")

    arms = arms or list(ARMS)
    done = {r["cq_id"]: r for r in json.load(open(CKPT))} if CKPT.exists() else {}
    results = list(done.values())

    for i, cq in enumerate(cqs, 1):
        if cq["cq_id"] in done:
            continue
        payload = understand_query(cq["question"])
        if payload is None:
            print(f"[{cq['cq_id']}] router failed — skipped")
            continue

        row = {**cq, "router_intent": payload.intent, "arms": {}}
        for name in arms:
            t0 = time.time()
            cfg   = ARMS[name]
            trace = _run(payload, cq["question"], **cfg)
            # An arm that retrieved nothing has no grounding. Any citation it
            # produces comes from the model's parametric memory, not the system.
            grounded = bool(trace["kg"]) or bool(trace["rag"])
            row["arms"][name] = {
                "citation":      score_citation(trace, cq),
                "regulation":    score_regulation_set(trace, cq),
                "answerable":    score_answerability(trace, cq, cfg.get("use_kg", False)),
                "hallucination": score_hallucination(trace, cq),
                "concept_cov":   score_concepts(trace, cq),
                "deontic":       score_deontic(trace, gold, cq),
                "grounded":      grounded,
                "n_kg":          len(trace["kg"]),
                "n_rag":         len(trace["rag"]),
                "latency_s":     round(time.time() - t0, 2),
            }
            m   = row["arms"][name]
            ans = "-" if m["answerable"] is None else f"{m['answerable']:.0f}"
            flag = "" if grounded else "  <NO CONTEXT>"
            print(f"  [{name:22}] faithF1={m['citation']['faithful_f1']:.2f} "
                  f"F1={m['citation']['f1']:.2f} ans={ans} "
                  f"hall={m['hallucination']:.2f} "
                  f"cov={m['concept_cov']:.0%} kg={m['n_kg']}{flag}")
            time.sleep(RATE_DELAY)

        results.append(row)
        json.dump(results, open(CKPT, "w"), indent=2)
        print(f"[{i}/{len(cqs)}] {cq['cq_id']} done")

    report(results, arms)


def report(results, arms):
    know = [r for r in results if r["intent"] == "knowledge"]
    scen = [r for r in results if r["intent"] == "scenario"]

    def avg(xs):
        xs = [x for x in xs if x is not None]
        return mean(xs) if xs else float("nan")

    print("\n" + "=" * 96)
    print(f"KNOWLEDGE QUESTIONS  (n={len(know)})")
    print(f"{'arm':22}{'faith_F1':>10}{'cite_F1':>9}{'answer':>9}"
          f"{'halluc':>9}{'concept':>9}{'deontic':>9}{'ungrnd':>9}")
    print("-" * 96)
    f1s = {}
    for a in arms:
        rows = [r["arms"][a] for r in know if a in r["arms"]]
        if not rows:
            continue
        f1s[a] = [x["citation"]["faithful_f1"] for x in rows]   # headline
        naive  = [x["citation"]["f1"] for x in rows]
        ung  = [x for x in rows if not x.get("grounded", True)]
        deon = [x["deontic"] for x in rows if x["deontic"] is not None]
        ansv = avg([x["answerable"] for x in rows])
        print(f"{a:22}"
              f"{mean(f1s[a]):10.3f}"
              f"{mean(naive):9.3f}"
              f"{('      -' if ansv != ansv else f'{ansv:9.3f}')}"
              f"{mean(x['hallucination'] for x in rows):9.3f}"
              f"{mean(x['concept_cov'] for x in rows):9.3f}"
              f"{(mean(deon) if deon else float('nan')):9.3f}"
              f"{len(ung):9d}")
    print("\n  faith_F1 = HEADLINE. A citation counts only if the system RETRIEVED that")
    print("             article. An article the retriever never surfaced was recalled")
    print("             from the model's parameters, not retrieved. Report this one.")
    print("  cite_F1  = naive F1, shown for transparency. Inflated by parametric memory.")
    print("  halluc   = fraction of citations with no support in retrieved context.")
    print("             faith_F1 == cite_F1 exactly when halluc == 0.")
    print("  ungrnd   = questions answered with a completely EMPTY context.")
    print("  answer   = '-' for arms that never query the graph.")

    if scen:
        print(f"\nSCENARIO QUESTIONS  (n={len(scen)})  — scored on regulation set")
        print(f"{'arm':22}{'reg_F1':>9}{'reg_P':>9}{'reg_R':>9}")
        print("-" * 96)
        for a in arms:
            rows = [r["arms"][a]["regulation"] for r in scen
                    if a in r["arms"] and r["arms"][a]["regulation"]]
            if rows:
                print(f"{a:22}{mean(x['f1'] for x in rows):9.3f}"
                      f"{mean(x['precision'] for x in rows):9.3f}"
                      f"{mean(x['recall'] for x in rows):9.3f}")

    if "rag_only" in f1s:
        print(f"\nPaired bootstrap vs rag_only, {N_BOOTSTRAP} resamples, seed={SEED}")
        print("95% CI on delta-FAITHFUL-F1 (knowledge questions). * = CI excludes zero.")
        print("-" * 96)
        base = f1s["rag_only"]
        for a in arms:
            if a == "rag_only" or a not in f1s:
                continue
            d, lo, hi, p = bootstrap_ci(f1s[a], base)
            sig = "*" if (lo > 0 or hi < 0) else " "
            print(f"  {a:22} d={d:+.3f}  [{lo:+.3f}, {hi:+.3f}]  p={p:.4f} {sig}")

    print("\nPer-group faithful F1 (hybrid). Report n alongside every figure.")
    print("-" * 96)
    for g in sorted({r["group"] for r in results}):
        rows = [r["arms"]["hybrid"]["citation"]["faithful_f1"]
                for r in results if r["group"] == g and "hybrid" in r["arms"]]
        if rows:
            warn = "  <- n<8, indicative only" if len(rows) < 8 else ""
            print(f"  group {g}  n={len(rows):2}  F1={mean(rows):.3f}{warn}")

    json.dump(results, open(OUT_DIR / "ablation_results.json", "w"), indent=2)
    print(f"\nWrote {OUT_DIR/'ablation_results.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms",   nargs="*", default=None)
    ap.add_argument("--groups", nargs="*", default=None)
    ap.add_argument("--reset",  action="store_true")
    args = ap.parse_args()
    if args.reset and CKPT.exists():
        CKPT.unlink()
    main(args.arms, args.groups)