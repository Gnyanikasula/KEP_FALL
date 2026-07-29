"""
Phase 1 — freeze what kg_retrieve returns, before anything is refactored.

Reads the 65 router payloads already cached in results/context_audit/
cached_payloads.json, so this costs ZERO LLM calls. Only Aura needs to be awake.

Two outputs:

  1. results/context_audit/kg_baseline.json
     Per question: the ordered rows kg_retrieve returned, plus the article set.
     This is the regression fixture every later phase is checked against.

  2. A variance report printed to stdout.
     kg_retrieve's Cypher orders by (confidence DESC, typed DESC) and LIMITs.
     Confidences are coarse — 0.9 / 0.85 / 0.8 / 0.7 — so tie groups are large,
     and Neo4j does not guarantee a stable order within ties. Run with
     --repeat 3 BEFORE trusting any parity assertion: it tells you how much the
     primary disagrees with *itself*, which is the floor for what "identical"
     can mean. If a question is unstable here, it cannot be asserted strictly
     later; the test marks it tolerant instead.

Usage
-----
    python scripts/snapshot_kg_baseline.py --repeat 3
    python scripts/snapshot_kg_baseline.py --store local     # local read-model
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from kep_fall import config

PAYLOADS = config.AUDIT_RESULTS_DIR / "cached_payloads.json"
BASELINE = config.AUDIT_RESULTS_DIR / "kg_baseline.json"


def row_signature(r: dict) -> list:
    """The fields that must not drift. Deliberately excludes chunk_ids text and
    anything cosmetic — this is about *which edge*, not how it renders."""
    return [r.get("subject"), r.get("predicate"), r.get("object"),
            r.get("article_id"), r.get("deontic")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1,
                    help="run each question N times to measure instability")
    ap.add_argument("--store", choices=["neo4j", "local"], default=None,
                    help="force a backend (sets STORE before importing engine)")
    ap.add_argument("--top-k", type=int, default=12)
    args = ap.parse_args()

    if args.store:
        os.environ["STORE"] = args.store

    # Imported after STORE is set, so the store singleton picks it up.
    from kep_fall.phase_d_engine.engine import kg_retrieve
    from kep_fall.phase_d_engine.router import QueryPayload

    if not PAYLOADS.exists():
        print(f"missing {PAYLOADS}\n"
              f"run kep_fall/phase_e_eval/context_audit/step1_cache_payloads.py first",
              file=sys.stderr)
        return 1

    payloads = json.load(open(PAYLOADS, encoding="utf-8"))
    print(f"{len(payloads)} cached payloads · store="
          f"{args.store or 'default'} · repeat={args.repeat}\n")

    baseline: dict = {}
    unstable: dict = {}

    for cq_id in sorted(payloads):
        try:
            payload = QueryPayload(**payloads[cq_id])
        except Exception as exc:
            print(f"  {cq_id}: payload rejected ({exc})", file=sys.stderr)
            continue

        runs = []
        for _ in range(args.repeat):
            rows = kg_retrieve(payload, top_k=args.top_k)
            runs.append(rows)

        first = runs[0]
        art_sets = [tuple(sorted({r.get("article_id") for r in run}))
                    for run in runs]
        sig_lists = [[row_signature(r) for r in run] for run in runs]

        stable_articles = len(set(art_sets)) == 1
        stable_order = all(s == sig_lists[0] for s in sig_lists)

        baseline[cq_id] = {
            "n": len(first),
            "articles": sorted({r.get("article_id") for r in first}),
            "regulations": sorted({r.get("regulation") for r in first
                                   if r.get("regulation")}),
            "rows": [row_signature(r) for r in first],
            "stable_articles": stable_articles,
            "stable_order": stable_order,
        }
        if not stable_articles:
            unstable[cq_id] = {
                "variants": [list(a) for a in sorted(set(art_sets))]
            }

        flag = "" if stable_articles else "  <- ARTICLE SET UNSTABLE"
        if stable_articles and not stable_order:
            flag = "  (order varies, articles stable)"
        print(f"  {cq_id}: {len(first):2d} rows, "
              f"{len(baseline[cq_id]['articles'])} articles{flag}")

    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"top_k": args.top_k,
               "store": args.store or "default",
               "repeat": args.repeat,
               "questions": baseline},
              open(BASELINE, "w", encoding="utf-8"), indent=1)

    n_unstable_art = sum(1 for v in baseline.values()
                         if not v["stable_articles"])
    n_unstable_ord = sum(1 for v in baseline.values()
                         if v["stable_articles"] and not v["stable_order"])
    empty = [k for k, v in baseline.items() if v["n"] == 0]

    print(f"\nwrote {BASELINE}")
    print(f"  questions          : {len(baseline)}")
    print(f"  empty retrievals   : {len(empty)} {empty if empty else ''}")
    if args.repeat > 1:
        print(f"  unstable articles  : {n_unstable_art}")
        print(f"  unstable order only: {n_unstable_ord}")
        if n_unstable_art:
            print("\n  Neo4j disagrees with itself on these — parity must be "
                  "asserted tolerantly for them:")
            for k, v in unstable.items():
                print(f"    {k}: {len(v['variants'])} distinct article sets")
    else:
        print("  (run with --repeat 3 to measure instability before "
              "relying on this fixture)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())