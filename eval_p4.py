#!/usr/bin/env python3
"""
eval_phase4.py — SHIELD Phase 4 Evaluation
60 CQs x 3 modes (hybrid / kg_only / rag_only)

Checkpoints after every question. Safe to interrupt and resume at any time.

Usage:
  python eval_phase4.py               # full run, auto-resumes if checkpoint exists
  python eval_phase4.py --quick       # first 5 CQs (dev)
  python eval_phase4.py --group D     # one regulation group
  python eval_phase4.py --mode hybrid # one mode only
  python eval_phase4.py --reset       # delete checkpoint and start fresh
"""

import os, re, sys, json, time, csv, argparse
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from route import understand_query, QueryPayload
from verdict import (
    kg_retrieve, rag_retrieve, rag_knowledge,
    build_context, _synthesize,
    SYSTEM, SYSTEM_KNOWLEDGE,
    analyze_trace,
)

CQ_PATH    = "eval_questions_full.json"
GOLD_PATH  = "gold_standard_full.json"
CKPT_PATH  = "Results/eval_phase4_checkpoint.json"
OUT_JSON   = "Results/eval_phase4_results.json"
OUT_CSV    = "Results/eval_phase4_summary.csv"
RATE_DELAY = 2.5

FLEXIBLE_GROUPS = {"C"}

GROUP_LABELS = {
    "A": "GDPR (15 CQs)",
    "B": "EU AI Act (18 CQs)",
    "C": "Cross-Regulation (5 CQs)",
    "D": "EU MDR 2017/745 (10 CQs)",
    "E": "UK MDR 2002 (8 CQs)",
    "F": "DUAA 2025 (4 CQs)",
}


def load_cqs(path: str, group: str = None) -> list[dict]:
    cqs = json.load(open(path, encoding="utf-8"))
    if group:
        cqs = [c for c in cqs if c["cq_id"][0] == group.upper()]
    print(f"Loaded {len(cqs)} CQs" + (f" (group {group})" if group else ""))
    return cqs


def load_gold(path: str) -> dict[str, list]:
    data  = json.load(open(path, encoding="utf-8"))
    index = defaultdict(list)
    for ann in data["annotations"]:
        index[_to_article_level(ann["chunk_id"])].append(ann)
    print(f"Loaded {len(data['annotations'])} annotations -> {len(index)} article keys")
    return dict(index)


def _to_article_level(chunk_id: str) -> str:
    parts, result = chunk_id.split("_"), []
    for p in parts:
        result.append(p)
        if p.startswith(("Art", "S80", "Part", "Schedule", "Annex")):
            break
    return "_".join(result)


def ckpt_load(path: str) -> dict[str, dict]:
    if not os.path.exists(path):
        return {}
    try:
        data = json.load(open(path, encoding="utf-8"))
        done = {r["cq_id"]: r for r in data if "modes" in r}
        if done:
            print(f"  [checkpoint] {len(done)} questions already done -> resuming")
        return done
    except Exception:
        return {}


def ckpt_save(results: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(results, open(path, "w", encoding="utf-8"), indent=2)


def _extract_articles(text: str) -> set[str]:
    found = set()
    for m in re.finditer(r'[Aa]rt(?:icle)?\.?\s*(\d+)', text):
        found.add(m.group(1))
    for m in re.finditer(r'[Aa]nnex\s+(I{1,3}V?|VI*|[IV]+|\d+)', text):
        found.add("annex " + m.group(1).lower())
    for m in re.finditer(r'[Ss]80[-\s]?22([A-Da-d])', text):
        found.add("s80-22" + m.group(1).lower())
    for m in re.finditer(r'[Ss]chedule\s+(\d+)', text):
        found.add("schedule " + m.group(1))
    for m in re.finditer(r'[Pp]art\s*(4A|\d+[A-Z]?)', text):
        found.add("part " + m.group(1).lower())
    return found


def _response_text(trace: dict) -> str:
    return " ".join(filter(None, [
        trace.get("reasoning", ""),
        " ".join(trace.get("rules", [])),
    ]))


def score_intent(trace: dict, cq: dict) -> float:
    intent = trace.get("intent", "")
    if cq["cq_id"][0] in FLEXIBLE_GROUPS:
        return 1.0 if intent in ("knowledge", "scenario") else 0.0
    return 1.0 if intent == "knowledge" else 0.0


def score_citation(trace: dict, cq: dict) -> dict:
    expected = _extract_articles(cq.get("articles", ""))
    if not expected:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0,
                "expected": [], "found": [], "missing": []}
    cited = _extract_articles(_response_text(trace))
    tp        = len(expected & cited)
    precision = tp / len(cited)    if cited    else 0.0
    recall    = tp / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 3), "recall": round(recall, 3),
        "f1": round(f1, 3), "expected": sorted(expected),
        "found": sorted(cited), "missing": sorted(expected - cited),
    }


def _camel_split(s: str) -> str:
    return re.sub(r"([A-Z])", r" \1", s).strip().lower()


def score_concepts(trace: dict, cq: dict) -> dict:
    concepts = [c.strip() for c in cq.get("key_concepts", "").split(";") if c.strip()]
    if not concepts:
        return {"coverage": 1.0, "found": [], "missing": []}
    text = _response_text(trace).lower()
    found, missing = [], []
    for c in concepts:
        (found if any(v in text for v in {c.lower(), _camel_split(c)}) else missing).append(c)
    return {"coverage": round(len(found) / len(concepts), 3),
            "found": found, "missing": missing}


def score_deontic(trace: dict, gold_index: dict) -> dict:
    rag_ids = {_to_article_level(c.get("chunk_id", "")) for c in trace.get("rag", [])}
    matched = [ann for aid, anns in gold_index.items()
               if aid in rag_ids for ann in anns]
    if not matched:
        return {"deontic_score": None, "checked": False, "annotations_matched": 0}
    vocab = {
        "obligation":          ["must", "shall", "required", "obligation", "duty"],
        "prohibition":         ["prohibited", "forbidden", "must not", "shall not", "banned"],
        "permission":          ["may", "permitted", "allowed", "can", "exception", "exemption"],
        "classification_rule": ["classified", "classification", "category", "qualifies", "defined"],
    }
    text   = _response_text(trace).lower()
    scores = [1.0 if any(m in text for m in vocab.get(a.get("deontic_type", ""), []))
              else 0.0 for a in matched]
    return {"deontic_score": round(sum(scores) / len(scores), 3),
            "checked": True, "annotations_matched": len(matched)}


def _empty_trace(question: str, payload: QueryPayload) -> dict:
    return {"question": question, "intent": payload.intent,
            "parsed": payload.model_dump(), "kg": [], "rag": [],
            "verdict": None, "rules": [], "reasoning": "", "confidence": 0}


def _apply(trace: dict, result) -> None:
    if result:
        trace.update(verdict=result.verdict, rules=result.rules,
                     reasoning=result.reasoning, confidence=result.confidence)


def run_hybrid(question: str, payload: QueryPayload) -> dict:
    return analyze_trace(question)


def run_kg_only(question: str, payload: QueryPayload) -> dict:
    trace = _empty_trace(question, payload)
    kg = kg_retrieve(payload)
    trace["kg"] = kg
    ctx = build_context(kg, [])
    if payload.intent == "knowledge":
        _apply(trace, _synthesize(SYSTEM_KNOWLEDGE,
               f"QUESTION: {question}\n\nTOPIC: {payload.topic}\n\nCONTEXT:\n{ctx[:6000]}"))
    else:
        _apply(trace, _synthesize(SYSTEM,
               f"QUESTION: {question}\n\nPARSED: {payload.model_dump()}\n\nCONTEXT:\n{ctx}"))
    return trace


def run_rag_only(question: str, payload: QueryPayload) -> dict:
    trace = _empty_trace(question, payload)
    rag = rag_knowledge(payload) if payload.intent == "knowledge" else rag_retrieve(payload)
    trace["rag"] = rag
    ctx = build_context([], rag)
    if payload.intent == "knowledge":
        _apply(trace, _synthesize(SYSTEM_KNOWLEDGE,
               f"QUESTION: {question}\n\nTOPIC: {payload.topic}\n\nCONTEXT:\n{ctx[:6000]}"))
    else:
        _apply(trace, _synthesize(SYSTEM,
               f"QUESTION: {question}\n\nPARSED: {payload.model_dump()}\n\nCONTEXT:\n{ctx}"))
    return trace


MODE_RUNNERS = {"hybrid": run_hybrid, "kg_only": run_kg_only, "rag_only": run_rag_only}


def evaluate_question(cq: dict, gold_index: dict, modes: list[str]) -> dict:
    question = cq["question"]
    print(f"\n  [{cq['cq_id']}] {question[:68]}...")

    payload = understand_query(question)
    if not payload:
        print("    [WARN] routing failed")
        return {"cq_id": cq["cq_id"], "error": "routing_failed", "group": cq["cq_id"][0]}

    print(f"    intent={payload.intent}  topic={str(payload.topic)[:40]}")

    result = {
        "cq_id": cq["cq_id"], "question": question,
        "regulation": cq["regulation"], "articles": cq["articles"],
        "key_concepts": cq["key_concepts"], "group": cq["cq_id"][0],
        "intent": payload.intent, "modes": {},
    }

    for mode in modes:
        print(f"    [{mode}] ", end="", flush=True)
        t0    = time.time()
        trace = MODE_RUNNERS[mode](question, payload)
        elapsed = time.time() - t0
        scores = {
            "intent_correct": score_intent(trace, cq),
            "citation":       score_citation(trace, cq),
            "concepts":       score_concepts(trace, cq),
            "deontic":        score_deontic(trace, gold_index),
            "kg_hits":        len(trace.get("kg", [])),
            "rag_hits":       len(trace.get("rag", [])),
            "confidence":     trace.get("confidence", 0),
            "verdict":        trace.get("verdict", ""),
            "rules":          trace.get("rules", []),
            "reasoning":      trace.get("reasoning", "")[:300],
            "elapsed_s":      round(elapsed, 1),
        }
        result["modes"][mode] = scores
        print(f"F1={scores['citation']['f1']:.2f}  "
              f"cov={scores['concepts']['coverage']:.0%}  "
              f"kg={scores['kg_hits']}  rag={scores['rag_hits']}  "
              f"intent={'ok' if scores['intent_correct'] else 'WRONG'}  "
              f"({elapsed:.1f}s)")
        time.sleep(RATE_DELAY)

    return result


def _mean(vals: list) -> float:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else 0.0


def aggregate(results: list[dict], modes: list[str]) -> dict:
    groups = sorted({r["group"] for r in results if "modes" in r})
    agg    = {"overall": {}, "by_group": {g: {} for g in groups}}

    def _compute(subset: list, mode: str) -> dict:
        valid = [r for r in subset if "modes" in r and mode in r["modes"]]
        if not valid:
            return {}
        get = lambda r, k, d=0: r["modes"][mode].get(k, d)
        deontic_vals = [get(r, "deontic", {}).get("deontic_score")
                        for r in valid if get(r, "deontic", {}).get("checked")]
        return {
            "n":               len(valid),
            "intent_acc":      _mean([get(r, "intent_correct") for r in valid]),
            "citation_f1":     _mean([get(r, "citation", {}).get("f1", 0) for r in valid]),
            "citation_prec":   _mean([get(r, "citation", {}).get("precision", 0) for r in valid]),
            "citation_recall": _mean([get(r, "citation", {}).get("recall", 0) for r in valid]),
            "concept_cov":     _mean([get(r, "concepts", {}).get("coverage", 0) for r in valid]),
            "kg_hit_rate":     _mean([1.0 if get(r, "kg_hits") > 0 else 0.0 for r in valid]),
            "avg_kg_triples":  _mean([get(r, "kg_hits") for r in valid]),
            "avg_rag_chunks":  _mean([get(r, "rag_hits") for r in valid]),
            "avg_confidence":  _mean([get(r, "confidence") for r in valid]),
            "deontic_align":   _mean(deontic_vals) if deontic_vals else None,
        }

    for mode in modes:
        agg["overall"][mode] = _compute(results, mode)
        for g in groups:
            agg["by_group"][g][mode] = _compute(
                [r for r in results if r.get("group") == g], mode)
    return agg


def print_results(results: list[dict], agg: dict, modes: list[str]) -> None:
    W = 82
    print("\n" + "=" * W)
    print("  SHIELD Phase 4 — Ablation Study Results")
    print("=" * W)

    print("\n-- OVERALL -------------------------------------------------------------------")
    print(f"{'Mode':<12} {'n':>3}  {'IntAcc':>7} {'CitF1':>7} {'Prec':>6} "
          f"{'Rec':>6} {'ConCov':>7} {'KGHit%':>7} {'Conf':>6} {'Deon':>6}")
    print("-" * W)
    for mode in modes:
        m = agg["overall"].get(mode, {})
        if not m: continue
        deo = f"{m['deontic_align']:.2f}" if m.get("deontic_align") is not None else "  n/a"
        print(f"{mode:<12} {m['n']:>3}  "
              f"{m['intent_acc']:>7.1%} {m['citation_f1']:>7.3f} "
              f"{m['citation_prec']:>6.3f} {m['citation_recall']:>6.3f} "
              f"{m['concept_cov']:>7.1%} {m['kg_hit_rate']:>7.1%} "
              f"{m['avg_confidence']:>5.0f}% {deo:>6}")

    print("\n-- BY GROUP ------------------------------------------------------------------")
    for g in sorted(agg["by_group"].keys()):
        print(f"\n  {GROUP_LABELS.get(g, g)}")
        print(f"  {'Mode':<12} {'CitF1':>7} {'ConCov':>7} {'KGHit%':>7} "
              f"{'AvgKG':>6} {'AvgRAG':>7} {'Conf':>6}")
        print("  " + "-" * 55)
        for mode in modes:
            m = agg["by_group"][g].get(mode, {})
            if not m: continue
            print(f"  {mode:<12} {m['citation_f1']:>7.3f} {m['concept_cov']:>7.1%} "
                  f"{m['kg_hit_rate']:>7.1%} {m['avg_kg_triples']:>6.1f} "
                  f"{m['avg_rag_chunks']:>7.1f} {m['avg_confidence']:>5.0f}%")

    print("\n-- PER-QUESTION --------------------------------------------------------------")
    for r in results:
        if "error" in r:
            print(f"  [{r['cq_id']}] ERROR: {r['error']}")
            continue
        print(f"\n  [{r['cq_id']}] {r['question'][:62]}")
        print(f"  Expected: {r['articles']}")
        for mode in modes:
            m   = r["modes"].get(mode, {})
            cit = m.get("citation", {})
            ms  = f"  MISSING={cit.get('missing', [])}" if cit.get("missing") else ""
            print(f"    {mode:<10} F1={cit.get('f1',0):.2f} "
                  f"rec={cit.get('recall',0):.2f} "
                  f"cov={m.get('concepts',{}).get('coverage',0):.0%} "
                  f"kg={m.get('kg_hits',0)} rules={m.get('rules',[])} {ms}")

    print("\n" + "=" * W)


def save_json(results: list[dict], agg: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    out = {"metadata": {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "total_cqs": len(results)},
           "aggregate": agg, "per_question": results}
    json.dump(out, open(path, "w", encoding="utf-8"), indent=2)
    print(f"\nResults JSON -> {path}")


def save_csv(agg: dict, modes: list[str], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rows = []
    for mode in modes:
        m = agg["overall"].get(mode, {})
        if m: rows.append({"scope": "overall", "group": "all", "mode": mode, **m})
        for g, gd in agg["by_group"].items():
            gm = gd.get(mode, {})
            if gm: rows.append({"scope": "group", "group": g, "mode": mode, **gm})
    if rows:
        w = csv.DictWriter(open(path, "w", newline="", encoding="utf-8"),
                           fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
        print(f"Results CSV  -> {path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode",  choices=["hybrid", "kg_only", "rag_only"])
    p.add_argument("--group", help="A/B/C/D/E/F")
    p.add_argument("--quick", action="store_true")
    p.add_argument("--reset", action="store_true", help="Delete checkpoint and start fresh")
    p.add_argument("--cq",   default=CQ_PATH)
    p.add_argument("--gold", default=GOLD_PATH)
    p.add_argument("--out",  default=OUT_JSON)
    p.add_argument("--csv",  default=OUT_CSV)
    args = p.parse_args()

    if args.reset and os.path.exists(CKPT_PATH):
        os.remove(CKPT_PATH)
        print("Checkpoint deleted — starting fresh")

    modes = [args.mode] if args.mode else ["hybrid", "kg_only", "rag_only"]

    print("=" * 82)
    print("  SHIELD — Phase 4 Evaluation")
    print(f"  Regulations: GDPR . EU AI Act . EU MDR . UK MDR . DUAA 2025")
    print(f"  Modes: {', '.join(modes)}")
    print("=" * 82)

    cqs      = load_cqs(args.cq, args.group)
    gold_idx = load_gold(args.gold)

    if args.quick:
        cqs = cqs[:5]
        print(f"  [--quick] {len(cqs)} CQs")

    completed = ckpt_load(CKPT_PATH)
    remaining = [c for c in cqs if c["cq_id"] not in completed]
    if completed:
        print(f"  {len(completed)} done, {len(remaining)} remaining")

    est = len(remaining) * len(modes) * (2 + RATE_DELAY) / 60
    print(f"\n  {len(cqs)} CQs x {len(modes)} modes | remaining ~{est:.0f} min\n")

    results = list(completed.values())

    for i, cq in enumerate(cqs, 1):
        if cq["cq_id"] in completed:
            print(f"[{i:>2}/{len(cqs)}] [{cq['cq_id']}] already done, skipping")
            continue

        print(f"[{i:>2}/{len(cqs)}]", end="")
        try:
            r = evaluate_question(cq, gold_idx, modes)
        except Exception as exc:
            print(f"\n  [ERROR] {cq['cq_id']}: {exc}")
            r = {"cq_id": cq["cq_id"], "group": cq["cq_id"][0], "error": str(exc)}

        results.append(r)
        completed[cq["cq_id"]] = r
        ckpt_save(results, CKPT_PATH)  # save after every question

    agg = aggregate(results, modes)
    print_results(results, agg, modes)
    save_json(results, agg, args.out)
    save_csv(agg, modes, args.csv)


if __name__ == "__main__":
    main()