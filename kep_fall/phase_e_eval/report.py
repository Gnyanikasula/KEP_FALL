"""
summarise_results.py — convert eval_p5_results.json to clean CSVs for the thesis.

Outputs (in Results/):
  summary_by_arm.csv       — one row per arm, all headline metrics
  summary_by_group.csv     — one row per (group × arm), citation + deontic
  per_question.csv         — one row per (question × arm), every metric
  bootstrap_cis.csv        — one row per arm, paired bootstrap vs rag_only

Usage:
  python summarise_results.py                          # uses Results/eval_p5_checkpoint.json
  python summarise_results.py path/to/results.json
"""

import csv, json, random, sys
from pathlib import Path
from statistics import mean
from kep_fall import config

# load
# src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Results/eval_p5_checkpoint.json")
# if not src.exists():
#     src = Path("Results/eval_p5_results.json")
src = Path(sys.argv[1]) if len(sys.argv) > 1 else config.ABLATION_CHECKPOINT
if not src.exists():
    src = config.ABLATION_RESULTS
R   = json.load(open(src, encoding="utf-8"))
# OUT = Path("Results"); OUT.mkdir(exist_ok=True)
OUT = config.EVAL_RESULTS_DIR
print(f"Loaded {len(R)} questions from {src}")

ARMS = ["hybrid", "kg_only", "rag_only"]
SEED, N = 20260710, 5000


# helpers
def ff(r, a):   return r["arms"][a]["citation"]["faithful_f1"]
def nf(r, a):   return r["arms"][a]["citation"]["f1"]
def hall(r, a): return r["arms"][a]["hallucination"]
def ans(r, a):  return r["arms"][a]["answerable"]
def cov(r, a):  return r["arms"][a]["concept_cov"]
def deon(r, a): return r["arms"][a]["deontic"]
def n_kg(r, a): return r["arms"][a]["n_kg"]
def n_rag(r,a): return r["arms"][a]["n_rag"]

def avgs(lst):  return round(mean(lst), 4) if lst else ""
def pct(v):     return f"{v:.1%}" if isinstance(v, float) else ""

def bootstrap(a_vals, b_vals):
    rng   = random.Random(SEED)
    deltas = [x - y for x, y in zip(a_vals, b_vals)]
    k      = len(deltas)
    boots  = sorted(
        mean([deltas[rng.randrange(k)] for _ in range(k)])
        for _ in range(N)
    )
    lo, hi = boots[int(.025 * N)], boots[int(.975 * N)]
    p      = 2 * min(sum(x <= 0 for x in boots),
                     sum(x >= 0 for x in boots)) / N
    return round(mean(deltas), 4), round(lo, 4), round(hi, 4), round(min(p, 1.0), 4)


know   = [r for r in R if r["intent"] == "knowledge"]
scen   = [r for r in R if r["intent"] == "scenario"]
groups = sorted({r["group"] for r in R})


# 1. summary_by_arm.csv
rows = []
for a in ARMS:
    pool = know  # all citation metrics on knowledge Qs only
    ff_v  = [ff(r, a)   for r in pool if a in r["arms"]]
    nf_v  = [nf(r, a)   for r in pool if a in r["arms"]]
    ha_v  = [hall(r, a) for r in pool if a in r["arms"]]
    co_v  = [cov(r, a)  for r in pool if a in r["arms"]]
    de_v  = [deon(r, a) for r in pool if a in r["arms"] and deon(r, a) is not None]
    an_v  = [ans(r, a)  for r in pool
             if a in r["arms"] and ans(r, a) is not None]
    ung   = sum(1 for r in pool if a in r["arms"]
                and not r["arms"][a].get("grounded", True))

    # scenario reg_F1
    sc_f1 = [r["arms"][a]["regulation"]["f1"]
              for r in scen if a in r["arms"]
              and r["arms"][a].get("regulation")]

    rows.append({
        "arm":              a,
        "n_knowledge":      len(pool),
        "faithful_F1":      avgs(ff_v),
        "naive_F1":         avgs(nf_v),
        "hallucination":    avgs(ha_v),
        "answerability":    avgs(an_v) if an_v else "N/A",
        "concept_cov":      avgs(co_v),
        "deontic_align":    avgs(de_v),
        "deontic_n":        len(de_v),
        "ungrounded_Qs":    ung,
        "scenario_reg_F1":  avgs(sc_f1) if sc_f1 else "N/A",
        "n_scenario":       len(sc_f1),
    })

p = OUT / "summary_by_arm.csv"
with open(p, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print(f"  wrote {p}")


# 2. bootstrap_cis.csv
base_ff  = [ff(r,  "rag_only") for r in know if "rag_only" in r["arms"]]
base_de  = [deon(r,"rag_only") for r in know
            if "rag_only" in r["arms"] and deon(r,"rag_only") is not None]

rows = []
for a in [arm for arm in ARMS if arm != "rag_only"]:
    arm_ff = [ff(r, a) for r in know if a in r["arms"]]
    d, lo, hi, p = bootstrap(arm_ff, base_ff)
    rows.append({
        "arm":              a,
        "metric":           "faithful_F1",
        "vs":               "rag_only",
        "n":                len(arm_ff),
        "delta":            d,
        "CI_lo_95":         lo,
        "CI_hi_95":         hi,
        "p_two_sided":      p,
        "significant":      "YES" if (lo > 0 or hi < 0) else "NO",
    })

    arm_de = [deon(r, a) for r in know
              if a in r["arms"] and deon(r, a) is not None]
    de_base = [deon(r, "rag_only") for r in know
               if a in r["arms"]
               and deon(r, a) is not None
               and deon(r, "rag_only") is not None]
    if arm_de and de_base and len(arm_de) == len(de_base):
        d2, lo2, hi2, p2 = bootstrap(arm_de, de_base)
        rows.append({
            "arm":          a,
            "metric":       "deontic_align",
            "vs":           "rag_only",
            "n":            len(arm_de),
            "delta":        d2,
            "CI_lo_95":     lo2,
            "CI_hi_95":     hi2,
            "p_two_sided":  p2,
            "significant":  "YES" if (lo2 > 0 or hi2 < 0) else "NO",
        })

p = OUT / "bootstrap_cis.csv"
with open(p, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print(f"  wrote {p}")


# 3. summary_by_group.csv
rows = []
for g in groups:
    gk = [r for r in know if r["group"] == g]
    gs = [r for r in scen if r["group"] == g]
    for a in ARMS:
        ff_v  = [ff(r, a) for r in gk if a in r["arms"]]
        nf_v  = [nf(r, a) for r in gk if a in r["arms"]]
        de_v  = [deon(r, a) for r in gk
                 if a in r["arms"] and deon(r, a) is not None]
        sc_v  = [r["arms"][a]["regulation"]["f1"]
                 for r in gs if a in r["arms"] and r["arms"][a].get("regulation")]
        rows.append({
            "group":            g,
            "arm":              a,
            "n":                len(gk) + len(gs),
            "warn_small_n":     "YES" if (len(gk) + len(gs)) < 8 else "",
            "faithful_F1":      avgs(ff_v),
            "naive_F1":         avgs(nf_v),
            "deontic_align":    avgs(de_v),
            "scenario_reg_F1":  avgs(sc_v) if sc_v else "",
        })

p = OUT / "summary_by_group.csv"
with open(p, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print(f"  wrote {p}")


# 4. per_question.csv
rows = []
for r in R:
    for a in ARMS:
        if a not in r["arms"]:
            continue
        arm_data = r["arms"][a]
        c        = arm_data["citation"]
        rows.append({
            "cq_id":            r["cq_id"],
            "group":            r["group"],
            "intent":           r["intent"],
            "question_type":    r["question_type"],
            "regulation":       r["regulation"],
            "article_ids":      "|".join(r["article_ids"]),
            "arm":              a,
            "faithful_F1":      round(c["faithful_f1"], 4),
            "naive_F1":         round(c["f1"], 4),
            "precision":        round(c.get("faithful_precision", c["precision"]), 4),
            "recall":           round(c.get("faithful_recall",    c["recall"]),    4),
            "citations_found":  "|".join(c["found"]),
            "citations_grounded": "|".join(c.get("found_grounded", [])),
            "citations_expected": "|".join(c["expected"]),
            "hallucination":    round(arm_data["hallucination"], 4),
            "answerability":    arm_data["answerable"] if arm_data["answerable"] is not None else "N/A",
            "concept_cov":      round(arm_data["concept_cov"], 4),
            "deontic_align":    round(arm_data["deontic"], 4) if arm_data["deontic"] is not None else "",
            "n_kg_triples":     arm_data["n_kg"],
            "n_rag_chunks":     arm_data["n_rag"],
            "grounded":         arm_data.get("grounded", True),
            "latency_s":        arm_data.get("latency_s", ""),
            "question":         r["question"],
        })

p = OUT / "per_question.csv"
with open(p, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print(f"  wrote {p}  ({len(rows)} rows)")

print(f"\nDone. All files in {OUT}/")