"""
kep_fall.phase_d_engine.graph_store — pluggable graph backend with fallback.

Why this exists
---------------
The runtime graph is 618 triples / 545 nodes. That is small enough to hold in
process, which means Neo4j Aura is a *convenience* on the read path, not a
necessity. On the Free tier Aura auto-pauses after 72h of inactivity and cannot
be resumed programmatically, so a paused instance would otherwise degrade the
system to rag_only silently — the worst possible failure, because it keeps
answering.

Design
------
Neo4j remains the system of record and the exploration surface. `LocalGraphStore`
is a *derived read-model* built from the same artefact that populates Aura
(`config.TRIPLES_CLEAN` + gold deontic annotations), reusing
`step5_load_graph.build_rows()` verbatim. Parity therefore holds by
construction: both stores are projections of one function's output, not two
independent implementations of the same idea.

A circuit breaker sits in front. Three consecutive Neo4j failures trip it to the
local store; a half-open probe every RECOVER_AFTER seconds tries to come back.
The active backend is always reported via `mode()` so the UI can show it —
degradation is never silent.

Determinism note
----------------
Neo4j's original ORDER BY (confidence DESC, typed DESC only) has no tiebreak,
and confidences are coarse (0.9 / 0.85 / 0.8 / 0.7), so tie groups are large.
The first version of this module tried to guess Aura's implicit tie order
(assumed = relationship creation order) and mirror it locally — that guess was
tested against a live parity run and falsified: Neo4j's actual tie resolution
did not match creation order, and is not documented or guaranteed to be stable
across query plans. Guessing an undocumented internal order is not a fix.

The real fix is to stop relying on implicit order at all: every ORDER BY below
carries an explicit tiebreak — (article_id, predicate, subject label, object
label) — added directly to the Cypher run against Neo4j. LocalGraphStore
sorts by the identical tuple. Both stores are now deterministic *by
construction*, not by inference about Aura's internals. Parity is asserted on
article sets in tests/test_graph_parity.py, and should now hold exactly rather
than needing a tolerant exemption — re-run scripts/snapshot_kg_baseline.py
after this change, since the previous baseline was captured under the old,
un-tiebroken ORDER BY and no longer reflects what Neo4j returns.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import List, Optional, Protocol

from kep_fall import config

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Row contract
# --------------------------------------------------------------------------
# Every store returns dicts with exactly these keys, matching the RETURN clause
# of the Cypher in engine.py. Downstream (_rank_triples, _bridge_hop consumers,
# _diversify_by_article, build_context) is store-agnostic and untouched.
ROW_KEYS = (
    "subject", "subject_uri", "subject_typed", "object_typed", "typed",
    "predicate", "object", "object_uri", "regulation", "article_id",
    "canonical_id", "chunk_ids", "confidence", "deontic", "deontic_source",
)


class GraphStore(Protocol):
    """Read-only graph access. Three calls cover every query engine.py makes."""

    name: str

    def match_by_keywords(self, keywords: List[str]) -> List[dict]:
        """Anchor match: edges whose subject/object label or uri, or whose
        predicate, contains any keyword (lowercased substring)."""
        ...

    def bridge_hop(self, anchor_labels: List[str],
                   seen_regs: List[str]) -> List[dict]:
        """Second hop: edges touching an anchor concept in regulations not
        already covered."""
        ...

    def fetch_by_article(self, article_ids: List[str]) -> List[dict]:
        """Article-anchored fetch for explicitly named provisions."""
        ...

    def healthy(self) -> bool:
        ...


# --------------------------------------------------------------------------
# Neo4j — the system of record. Cypher lifted unchanged from engine.py.
# --------------------------------------------------------------------------
_MATCH_CYPHER = """
    MATCH (s:Concept)-[r:REL]->(o:Concept)
    WHERE any(kw IN $keywords
              WHERE toLower(s.label)   CONTAINS kw
                 OR toLower(r.predicate) CONTAINS kw
                 OR (s.uri IS NOT NULL AND toLower(s.uri) CONTAINS kw))
    RETURN s.label AS subject, s.uri AS subject_uri, s.typed AS subject_typed,
           o.typed AS object_typed, s.typed AS typed, r.predicate AS predicate,
           o.label AS object, o.uri AS object_uri, r.regulation AS regulation,
           r.article_id AS article_id, r.canonical_id AS canonical_id,
           r.chunk_ids AS chunk_ids, r.confidence AS confidence,
           r.deontic AS deontic, r.deontic_source AS deontic_source
    ORDER BY r.confidence DESC, s.typed DESC, r.article_id, r.predicate, s.label, o.label
    LIMIT 30
    UNION
    MATCH (s:Concept)-[r:REL]->(o:Concept)
    WHERE any(kw IN $keywords
              WHERE toLower(o.label)   CONTAINS kw
                 OR toLower(r.predicate) CONTAINS kw
                 OR (o.uri IS NOT NULL AND toLower(o.uri) CONTAINS kw))
    RETURN s.label AS subject, s.uri AS subject_uri, s.typed AS subject_typed,
           o.typed AS object_typed, s.typed AS typed, r.predicate AS predicate,
           o.label AS object, o.uri AS object_uri, r.regulation AS regulation,
           r.article_id AS article_id, r.canonical_id AS canonical_id,
           r.chunk_ids AS chunk_ids, r.confidence AS confidence,
           r.deontic AS deontic, r.deontic_source AS deontic_source
    ORDER BY r.confidence DESC, s.typed DESC, r.article_id, r.predicate, s.label, o.label
    LIMIT 20
"""


class Neo4jGraphStore:
    """Live Cypher against Aura. Fails fast so the breaker can trip."""

    name = "neo4j"

    def __init__(self, driver_factory, database: str,
                 match_cypher: str = _MATCH_CYPHER,
                 bridge_cypher: str = "", by_article_cypher: str = ""):
        self._driver_factory = driver_factory
        self._database = database
        self._match = match_cypher
        self._bridge = bridge_cypher
        self._by_article = by_article_cypher

    def _run(self, cypher: str, **params) -> List[dict]:
        recs = self._driver_factory().execute_query(
            cypher, database_=self._database, **params
        ).records
        return [dict(r) for r in recs]

    def match_by_keywords(self, keywords: List[str]) -> List[dict]:
        return self._run(self._match, keywords=keywords)

    def bridge_hop(self, anchor_labels: List[str],
                   seen_regs: List[str]) -> List[dict]:
        return self._run(self._bridge, anchor_labels=anchor_labels,
                         seen_regs=seen_regs)

    def fetch_by_article(self, article_ids: List[str]) -> List[dict]:
        return self._run(self._by_article, article_ids=article_ids)

    def healthy(self) -> bool:
        try:
            self._driver_factory().verify_connectivity()
            return True
        except Exception:
            return False


# --------------------------------------------------------------------------
# Local read-model — derived from the SAME artefact that populates Aura.
# --------------------------------------------------------------------------
class LocalGraphStore:
    """
    In-process projection of the graph.

    Built by reusing step5_load_graph.build_rows(), which is the function whose
    output was written to Neo4j. Node identity, canonical_id, deontic and
    deontic_source are therefore not re-derived here — they are the same values,
    from the same code, over the same input file.

    Edge identity mirrors the Neo4j MERGE key:
        (s_key, predicate, article_id, o_key)
    so an edge that collapsed to one relationship in the graph collapses to one
    row here.
    """

    name = "local"

    def __init__(self, triples_path=None, gold_path=None):
        from kep_fall.phase_c_graph.step5_load_graph import (
            build_rows, load_gold_deontic,
        )
        from pathlib import Path

        triples_path = Path(triples_path or config.TRIPLES_CLEAN)
        gold_path = Path(gold_path or config.GOLD_STANDARD)

        triples = json.load(open(triples_path, encoding="utf-8"))
        gold = load_gold_deontic(gold_path)
        rows = build_rows(triples, gold)

        self._edges: List[dict] = []
        seen = set()
        for r in rows:
            key = (r["s_key"], r["pred"], r["art"], r["o_key"])
            if key in seen:
                continue
            seen.add(key)
            self._edges.append({
                "subject":        r["s_label"],
                "subject_uri":    r["s_uri"],
                "subject_typed":  r["s_typed"],
                "object_typed":   r["o_typed"],
                "typed":          r["s_typed"],
                "predicate":      r["pred"],
                "object":         r["o_label"],
                "object_uri":     r["o_uri"],
                "regulation":     r["reg"],
                "article_id":     r["art"],
                "canonical_id":   r["canon"],
                "chunk_ids":      list(r["chunks"] or []),
                "confidence":     r["conf"],
                "deontic":        r["deontic"],
                "deontic_source": r["deon_src"],
            })

        # Precomputed lowercase haystacks. Substring matching over 618 edges is
        # a linear scan either way; caching the casefold is the only thing worth
        # doing, and it keeps match_by_keywords well under a millisecond.
        self._hay = [{
            "s_label": (e["subject"] or "").lower(),
            "o_label": (e["object"] or "").lower(),
            "s_uri":   (e["subject_uri"] or "").lower(),
            "o_uri":   (e["object_uri"] or "").lower(),
            "pred":    (e["predicate"] or "").lower(),
        } for e in self._edges]

        self._by_article: dict[str, List[int]] = {}
        for i, e in enumerate(self._edges):
            self._by_article.setdefault(e["article_id"], []).append(i)

        log.info("LocalGraphStore ready: %d edges, %d articles",
                 len(self._edges), len(self._by_article))

    # -- ordering ---------------------------------------------------------
    def _sort_key(self, i: int):
        """
        Mirrors the Neo4j ORDER BY exactly:
            confidence DESC, subject_typed DESC,
            article_id, predicate, subject label, object label

        An earlier version tried to guess Neo4j's implicit tie order
        (assumed = file/creation order) instead of using an explicit
        tiebreak. That guess was tested against a live parity run and was
        wrong — Neo4j's actual tie resolution isn't documented or provably
        stable. Rather than reverse-engineer Aura's internals, the Cypher
        itself (graph_store._MATCH_CYPHER, engine._BRIDGE_CYPHER,
        engine._BY_ARTICLE_CYPHER) now carries this same explicit tiebreak,
        so both stores are forced to agree by construction.
        """
        e = self._edges[i]
        return (
            -(e["confidence"] or 0.0),
            0 if e["subject_typed"] else 1,
            e["article_id"] or "",
            e["predicate"] or "",
            e["subject"] or "",
            e["object"] or "",
        )

    def _ordered(self, idxs) -> List[dict]:
        return [self._edges[i] for i in sorted(idxs, key=self._sort_key)]

    # -- queries ----------------------------------------------------------
    def match_by_keywords(self, keywords: List[str]) -> List[dict]:
        kws = [k.lower() for k in keywords if k]
        if not kws:
            return []

        pass_a, pass_b = [], []
        for i, h in enumerate(self._hay):
            if any(k in h["s_label"] or k in h["pred"] or k in h["s_uri"]
                   for k in kws):
                pass_a.append(i)
            if any(k in h["o_label"] or k in h["pred"] or k in h["o_uri"]
                   for k in kws):
                pass_b.append(i)

        # Cypher UNION applies each LIMIT to its own branch, then dedupes on
        # the full returned row — which, since both branches project the same
        # columns off the same relationship, means dedupe on edge identity.
        out, seen = [], set()
        for e in [*self._ordered(pass_a)[:30], *self._ordered(pass_b)[:20]]:
            k = (e["subject"], e["predicate"], e["object"], e["article_id"])
            if k not in seen:
                seen.add(k)
                out.append(e)
        return out

    def bridge_hop(self, anchor_labels: List[str],
                   seen_regs: List[str]) -> List[dict]:
        wanted = {a.lower() for a in anchor_labels if a}
        blocked = set(seen_regs or [])
        if not wanted:
            return []
        hits = [
            i for i, h in enumerate(self._hay)
            if (h["s_label"] in wanted or h["o_label"] in wanted)
            and self._edges[i]["regulation"] not in blocked
        ]
        return self._ordered(hits)[:25]

    def fetch_by_article(self, article_ids: List[str]) -> List[dict]:
        idxs = []
        for aid in article_ids or []:
            idxs.extend(self._by_article.get(aid, []))
        return self._ordered(idxs)

    def healthy(self) -> bool:
        return bool(self._edges)


# --------------------------------------------------------------------------
# Circuit breaker
# --------------------------------------------------------------------------
class BreakerGraphStore:
    """
    Primary with automatic fallback.

    CLOSED  -> all calls to primary. FAIL_THRESHOLD consecutive failures trip.
    OPEN    -> all calls to fallback. After RECOVER_AFTER seconds, half-open.
    HALF    -> next call probes the primary. Success closes; failure re-opens.

    A per-call failure never propagates: the fallback answers instead. This is
    deliberate — kg_retrieve must not raise, because rag must still run.
    """

    FAIL_THRESHOLD = 3
    RECOVER_AFTER = 60.0

    def __init__(self, primary: GraphStore, fallback: GraphStore,
                 forced: Optional[str] = None):
        self.primary = primary
        self.fallback = fallback
        self._forced = forced
        self._fails = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    # -- state ------------------------------------------------------------
    def mode(self) -> str:
        """'full' when serving from the primary, 'replica' when not."""
        if self._forced == "local":
            return "replica"
        if self._forced == "neo4j":
            return "full"
        return "replica" if self._is_open() else "full"

    def _is_open(self) -> bool:
        if self._fails < self.FAIL_THRESHOLD:
            return False
        return (time.monotonic() - self._opened_at) < self.RECOVER_AFTER

    def _active(self) -> GraphStore:
        if self._forced == "local":
            return self.fallback
        if self._forced == "neo4j":
            return self.primary
        return self.fallback if self._is_open() else self.primary

    def _record(self, ok: bool) -> None:
        with self._lock:
            if ok:
                if self._fails:
                    log.info("graph_store: primary recovered, closing breaker")
                self._fails = 0
            else:
                self._fails += 1
                if self._fails == self.FAIL_THRESHOLD:
                    self._opened_at = time.monotonic()
                    log.warning(
                        "graph_store: breaker OPEN after %d failures — "
                        "serving from local read-model", self._fails)

    # -- dispatch ---------------------------------------------------------
    def _call(self, method: str, *args) -> List[dict]:
        store = self._active()
        try:
            rows = getattr(store, method)(*args)
            if store is self.primary:
                self._record(True)
            return rows
        except Exception as exc:
            if store is self.fallback:
                log.error("graph_store: local read-model failed on %s: %s",
                          method, exc)
                return []
            self._record(False)
            log.warning("graph_store: primary %s failed (%s) — falling back",
                        method, str(exc)[:160])
            try:
                return getattr(self.fallback, method)(*args)
            except Exception as exc2:
                log.error("graph_store: fallback also failed on %s: %s",
                          method, exc2)
                return []

    def match_by_keywords(self, keywords):
        return self._call("match_by_keywords", keywords)

    def bridge_hop(self, anchor_labels, seen_regs):
        return self._call("bridge_hop", anchor_labels, seen_regs)

    def fetch_by_article(self, article_ids):
        return self._call("fetch_by_article", article_ids)

    def healthy(self) -> bool:
        return self._active().healthy()


# --------------------------------------------------------------------------
# Startup self-check — the guard against a rotting cold standby
# --------------------------------------------------------------------------
_PROBE_KEYWORDS = [
    ["healthdata", "health"],
    ["consent", "explicit"],
    ["highriskaisystem", "risk"],
]


def self_check(breaker: BreakerGraphStore) -> dict:
    """
    Run three canned queries against BOTH stores and compare article sets.

    Called at startup. Costs ~50ms and answers the question a cold standby
    otherwise only answers at the worst possible moment: does the fallback
    still work, and does it still agree with the primary?
    """
    report = {"primary": None, "fallback": True, "agree": None, "detail": []}
    try:
        for kws in _PROBE_KEYWORDS:
            got = breaker.fallback.match_by_keywords(kws)
            report["detail"].append({"keywords": kws, "local_n": len(got)})
    except Exception as exc:
        report["fallback"] = False
        report["detail"].append({"error": str(exc)[:200]})
        log.error("graph_store self-check: LOCAL READ-MODEL BROKEN: %s", exc)
        return report

    try:
        agree = True
        for i, kws in enumerate(_PROBE_KEYWORDS):
            a = {r["article_id"] for r in breaker.primary.match_by_keywords(kws)}
            b = {r["article_id"] for r in breaker.fallback.match_by_keywords(kws)}
            report["detail"][i]["neo4j_articles"] = len(a)
            report["detail"][i]["local_articles"] = len(b)
            if a != b:
                agree = False
                report["detail"][i]["diff"] = sorted(a ^ b)[:10]
        report["primary"] = True
        report["agree"] = agree
        if agree:
            log.info("graph_store self-check: stores agree on all probes")
        else:
            log.warning("graph_store self-check: STORES DISAGREE — %s",
                        report["detail"])
    except Exception as exc:
        report["primary"] = False
        log.warning("graph_store self-check: primary unreachable (%s) — "
                    "local read-model verified and will serve", str(exc)[:160])
    return report


# --------------------------------------------------------------------------
# Singleton
# --------------------------------------------------------------------------
_STORE: Optional[BreakerGraphStore] = None


def get_store(driver_factory=None, database=None,
              bridge_cypher="", by_article_cypher="") -> BreakerGraphStore:
    """
    Build (once) the breaker-wrapped store.

    STORE=local  -> never touch Neo4j (test the fallback, or demo it deliberately)
    STORE=neo4j  -> never fall back (prove the primary is really being used)
    unset        -> Neo4j primary, automatic fallback
    """
    global _STORE
    if _STORE is not None:
        return _STORE

    forced = os.getenv("STORE", "").strip().lower() or None
    if forced not in (None, "local", "neo4j"):
        log.warning("graph_store: ignoring unknown STORE=%r", forced)
        forced = None

    local = LocalGraphStore()
    primary = Neo4jGraphStore(
        driver_factory, database,
        bridge_cypher=bridge_cypher, by_article_cypher=by_article_cypher,
    ) if driver_factory else local

    _STORE = BreakerGraphStore(primary, local, forced=forced)
    if forced:
        log.warning("graph_store: STORE=%s forced", forced)
    return _STORE


def reset_store() -> None:
    """Test hook."""
    global _STORE
    _STORE = None