"""
Parity: does the local read-model retrieve the same articles as Neo4j?

Runs entirely offline against the fixture written by
scripts/snapshot_kg_baseline.py, plus the cached router payloads. No LLM calls,
no network, no Aura. Safe for CI.

The assertion is on ARTICLE SETS, not row order, and questions the baseline
recorded as unstable are exempted from strict equality. That is not a weakened
test — it is the correct one. Neo4j's `ORDER BY confidence DESC, typed DESC`
with a LIMIT is not stable within ties, and confidences are coarse, so for some
questions the primary does not agree with itself run to run. Asserting strict
equality against a nondeterministic reference would produce a flaky test that
gets muted, which is worse than no test.

Run:
    pytest tests/test_graph_parity.py -v
"""
from __future__ import annotations

import json
import os

import pytest

from kep_fall import config

PAYLOADS = config.AUDIT_RESULTS_DIR / "cached_payloads.json"
BASELINE = config.AUDIT_RESULTS_DIR / "kg_baseline.json"

pytestmark = pytest.mark.skipif(
    not (PAYLOADS.exists() and BASELINE.exists()),
    reason="run scripts/snapshot_kg_baseline.py --repeat 3 first",
)


@pytest.fixture(scope="module")
def baseline():
    return json.load(open(BASELINE, encoding="utf-8"))


@pytest.fixture(scope="module")
def payloads():
    return json.load(open(PAYLOADS, encoding="utf-8"))


@pytest.fixture(scope="module")
def local_retrieve():
    """kg_retrieve bound to the local read-model, never touching Neo4j."""
    os.environ["STORE"] = "local"
    from kep_fall.phase_d_engine import graph_store
    graph_store.reset_store()
    from kep_fall.phase_d_engine.engine import kg_retrieve
    return kg_retrieve


def test_local_store_loads():
    from kep_fall.phase_d_engine.graph_store import LocalGraphStore
    s = LocalGraphStore()
    assert s.healthy()
    assert len(s._edges) > 500, "read-model looks truncated"
    assert len(s._by_article) > 40, "too few articles indexed"


def test_row_contract():
    """Every store must return the same keys engine.py's Cypher projects."""
    from kep_fall.phase_d_engine.graph_store import LocalGraphStore, ROW_KEYS
    rows = LocalGraphStore().match_by_keywords(["consent"])
    assert rows, "probe returned nothing"
    assert set(rows[0]) == set(ROW_KEYS)


def test_local_is_deterministic():
    """The read-model must not vary run to run — that is its whole point."""
    from kep_fall.phase_d_engine.graph_store import LocalGraphStore
    s = LocalGraphStore()
    kws = ["healthdata", "consent", "highriskaisystem"]
    runs = [[r["article_id"] for r in s.match_by_keywords(kws)]
            for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_article_parity(baseline, payloads, local_retrieve):
    """Local retrieval must reach the same articles Neo4j reached."""
    from kep_fall.phase_d_engine.router import QueryPayload

    top_k = baseline.get("top_k", 12)
    questions = baseline["questions"]

    strict_fail, tolerant_note = [], []
    for cq_id, expect in questions.items():
        if cq_id not in payloads:
            continue
        got = local_retrieve(QueryPayload(**payloads[cq_id]), top_k=top_k)
        got_arts = {r.get("article_id") for r in got}
        want_arts = set(expect["articles"])

        if got_arts == want_arts:
            continue
        if not expect.get("stable_articles", True):
            tolerant_note.append(cq_id)
            continue
        strict_fail.append((cq_id, sorted(want_arts - got_arts),
                            sorted(got_arts - want_arts)))

    if tolerant_note:
        print(f"\n{len(tolerant_note)} question(s) exempt "
              f"(Neo4j unstable on these): {tolerant_note}")

    assert not strict_fail, "\n" + "\n".join(
        f"  {cq}: missing={miss} extra={extra}"
        for cq, miss, extra in strict_fail
    )


def test_no_question_goes_empty(baseline, payloads, local_retrieve):
    """A question that retrieved edges via Neo4j must not retrieve none here.
    An empty KG result silently degrades that question to rag_only."""
    from kep_fall.phase_d_engine.router import QueryPayload

    top_k = baseline.get("top_k", 12)
    regressions = []
    for cq_id, expect in baseline["questions"].items():
        if expect["n"] == 0 or cq_id not in payloads:
            continue
        got = local_retrieve(QueryPayload(**payloads[cq_id]), top_k=top_k)
        if not got:
            regressions.append(cq_id)
    assert not regressions, f"empty under local store: {regressions}"