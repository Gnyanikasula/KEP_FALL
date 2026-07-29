"""
kep_fall.phase_d_engine.eval_data — serve the FROZEN evaluation results to the UI.

The numbers here are read verbatim from results/evaluation/*.csv, which are the
output of the offline ablation harness. Nothing is recomputed — this module only
reshapes the CSVs into JSON the eval explorer renders. If a number looks wrong in
the UI, it is wrong in the CSV; fix it upstream and re-run the harness, don't
patch it here.

Loaded once at import (the CSVs don't change at runtime) and cached.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from kep_fall import config

log = logging.getLogger(__name__)

_DIR = config.EVAL_RESULTS_DIR
_CACHE: Optional[dict] = None

# Metrics where HIGHER is better vs where LOWER is better — the UI needs to know
# which direction "good" points for the heatmap coloring.
HIGHER_BETTER = {"faithful_F1", "naive_F1", "answerability", "concept_cov",
                 "deontic_align", "scenario_reg_F1", "precision", "recall"}
LOWER_BETTER = {"hallucination", "latency_s"}


def _num(x):
    """Parse a CSV cell to float, tolerating '', 'N/A', and stray text."""
    if x is None:
        return None
    s = str(x).strip()
    if s in ("", "N/A", "NA", "nan", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _read_csv(name: str) -> list[dict]:
    path = _DIR / name
    if not path.exists():
        log.warning("eval_data: missing %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load() -> dict:
    # ── by-arm summary: the headline ablation table ──────────────────────
    arms = []
    for r in _read_csv("summary_by_arm.csv"):
        arms.append({
            "arm": r["arm"],
            "n_knowledge": int(_num(r.get("n_knowledge")) or 0),
            "faithful_F1": _num(r.get("faithful_F1")),
            "naive_F1": _num(r.get("naive_F1")),
            "hallucination": _num(r.get("hallucination")),
            "answerability": _num(r.get("answerability")),
            "concept_cov": _num(r.get("concept_cov")),
            "deontic_align": _num(r.get("deontic_align")),
            "ungrounded_Qs": int(_num(r.get("ungrounded_Qs")) or 0),
            "scenario_reg_F1": _num(r.get("scenario_reg_F1")),
            "n_scenario": int(_num(r.get("n_scenario")) or 0),
            # faithful minus naive: positive = honest, negative = parametric
            # leakage inflated the naive score. This gap is the headline finding.
            "faithful_naive_gap": (
                (_num(r.get("faithful_F1")) - _num(r.get("naive_F1")))
                if _num(r.get("faithful_F1")) is not None
                and _num(r.get("naive_F1")) is not None else None
            ),
        })

    # ── bootstrap CIs: the significance evidence, for error bars ─────────
    cis = []
    for r in _read_csv("bootstrap_cis.csv"):
        cis.append({
            "arm": r["arm"],
            "metric": r["metric"],
            "vs": r["vs"],
            "n": int(_num(r.get("n")) or 0),
            "delta": _num(r.get("delta")),
            "ci_lo": _num(r.get("CI_lo_95")),
            "ci_hi": _num(r.get("CI_hi_95")),
            "p": _num(r.get("p_two_sided")),
            "significant": str(r.get("significant", "")).strip().upper() == "YES",
        })

    # ── per-group: the heatmap (group × arm), with small-n honesty flag ──
    groups = []
    for r in _read_csv("summary_by_group.csv"):
        groups.append({
            "group": r["group"],
            "arm": r["arm"],
            "n": int(_num(r.get("n")) or 0),
            "warn_small_n": str(r.get("warn_small_n", "")).strip().upper() == "YES",
            "faithful_F1": _num(r.get("faithful_F1")),
            "naive_F1": _num(r.get("naive_F1")),
            "deontic_align": _num(r.get("deontic_align")),
            "scenario_reg_F1": _num(r.get("scenario_reg_F1")),
        })

    # ── per-question: the drill-down ────────────────────────────────────
    pq = []
    for r in _read_csv("per_question.csv"):
        pq.append({
            "cq_id": r["cq_id"],
            "group": r["group"],
            "intent": r.get("intent"),
            "question_type": r.get("question_type"),
            "regulation": r.get("regulation"),
            "arm": r["arm"],
            "faithful_F1": _num(r.get("faithful_F1")),
            "naive_F1": _num(r.get("naive_F1")),
            "precision": _num(r.get("precision")),
            "recall": _num(r.get("recall")),
            "citations_found": r.get("citations_found", ""),
            "citations_grounded": r.get("citations_grounded", ""),
            "citations_expected": r.get("citations_expected", ""),
            "hallucination": _num(r.get("hallucination")),
            "concept_cov": _num(r.get("concept_cov")),
            "deontic_align": _num(r.get("deontic_align")),
            "n_kg_triples": int(_num(r.get("n_kg_triples")) or 0),
            "n_rag_chunks": int(_num(r.get("n_rag_chunks")) or 0),
            "latency_s": _num(r.get("latency_s")),
            "question": r.get("question", ""),
        })

    # Distinct question list (collapsing the 3 arms) for the explorer's picker.
    seen, questions = set(), []
    for r in pq:
        if r["cq_id"] in seen:
            continue
        seen.add(r["cq_id"])
        questions.append({
            "cq_id": r["cq_id"], "group": r["group"],
            "intent": r["intent"], "question_type": r["question_type"],
            "regulation": r["regulation"], "question": r["question"],
        })

    arm_names = [a["arm"] for a in arms]
    group_names = sorted({g["group"] for g in groups})

    return {
        "arms": arms,
        "arm_names": arm_names,
        "bootstrap": cis,
        "groups": groups,
        "group_names": group_names,
        "per_question": pq,
        "questions": questions,
        "meta": {
            "n_questions": len(questions),
            "n_arms": len(arm_names),
            "higher_better": sorted(HIGHER_BETTER),
            "lower_better": sorted(LOWER_BETTER),
        },
    }


def get_eval() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = _load()
        log.info("eval_data loaded: %d questions, %d arms",
                 _CACHE["meta"]["n_questions"], _CACHE["meta"]["n_arms"])
    return _CACHE