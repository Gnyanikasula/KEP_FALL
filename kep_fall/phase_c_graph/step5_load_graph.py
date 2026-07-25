"""
Step 5 — AuraDB Population  (v2: deontic-annotated edges)

Loads data/clean_triples.json into Neo4j AuraDB.

Schema
------
  (:Concept {key, label, uri, typed, source_reg})
     -[:REL {predicate, predicate_uri, regulation, article_id,
             canonical_id, chunk_ids, confidence,
             deontic, deontic_source}]->
  (:Concept {...})

WHAT CHANGED vs v1
------------------
1. r.deontic          — obligation | prohibition | permission |
                        classification_rule | amendment
2. r.deontic_source   — "gold" | "predicate" | "none"
3. r.canonical_id     — canonical article key (EUAI_ArtAnnexIII), so
                        Neo4j, ChromaDB and the gold standard all join on
                        one identifier. No regex at query time.

WHY
---
Without a deontic property on the edge, the kg_only arm of the ablation
cannot be scored for deontic alignment — the metric returns None and the
arm becomes uncomparable. Storing it on the edge (as Turaga et al. do with
`type: SHALL_DO`) makes every arm scorable.

PROVENANCE OF THE DEONTIC VALUE
-------------------------------
Preference order, recorded in r.deontic_source:
  1. "gold"      — the human-annotated gold standard for that article.
                   This is a legal judgement and takes priority.
  2. "predicate" — derived from the DPV predicate. A weak fallback for
                   articles with no gold annotation.
  3. "none"      — neither available; edge carries deontic = null.

The fallback exists only so the graph is complete. Any edge whose
deontic_source is "predicate" should be treated as unverified: the
predicate vocabulary cannot express prohibition, so a prohibitive rule
extracted as hasObligation would be mislabelled.

Idempotent: MERGE on (key) and on (predicate, article_id).
Re-running is safe; batched in groups of 50.
"""

import json
import logging
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from kep_fall import config

from kep_fall.citation import canonical_from_kg

load_dotenv()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)
logging.getLogger("neo4j").setLevel(logging.WARNING)

# TRIPLES_PATH = Path("data/clean_triples.json")
# GOLD_PATH    = Path("gold_standard_full.json")
TRIPLES_PATH = config.TRIPLES_CLEAN
GOLD_PATH    = config.GOLD_STANDARD
BATCH_SIZE   = 50

URI      = os.getenv("NEO4J_URI")
USER     = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

VALID_DEONTIC = {"obligation", "prohibition", "permission",
                 "classification_rule", "amendment"}

# Fallback only. Note what is NOT here: there is no predicate in the DPV
# vocabulary that means "prohibition", so this map can never produce one.
# That is precisely why gold takes priority.
PREDICATE_DEONTIC = {
    "hasObligation":                    "obligation",
    "hasTechnicalMeasure":              "obligation",
    "hasOrganisationalMeasure":         "obligation",
    "hasTechnicalOrganisationalMeasure":"obligation",
    "hasNotice":                        "obligation",
    "hasRiskAssessment":                "obligation",
    "isMitigatedByMeasure":             "obligation",
    "hasLegalBasis":                    "permission",
    "hasRight":                         "permission",
    "hasRisk":                          None,
    "hasPurpose":                       None,
    "hasPersonalData":                  None,
    "hasDataSubject":                   None,
}


def load_gold_deontic(path: Path) -> dict:
    """canonical_article_id -> deontic_type, from the human annotations."""
    if not path.exists():
        log.warning(f"{path} not found — every edge falls back to predicate mapping")
        return {}
    doc = json.load(open(path, encoding="utf-8"))
    out = {}
    for a in doc["annotations"]:
        dt = a.get("deontic_type")
        if dt and dt not in VALID_DEONTIC:
            raise ValueError(f"{a['annotation_id']}: unknown deontic_type {dt!r}")
        out[a["article_id"]] = dt
    log.info(f"Gold deontic annotations: {len(out)} articles")
    return out


def resolve_deontic(canonical_id: str, predicate: str, gold: dict):
    """Returns (deontic, source). Gold wins; predicate is a labelled fallback."""
    if canonical_id in gold and gold[canonical_id]:
        return gold[canonical_id], "gold"
    d = PREDICATE_DEONTIC.get(predicate)
    return (d, "predicate") if d else (None, "none")


def node_key(label: str, uri, typed: bool) -> str:
    return uri if (typed and uri) else f"new:{label}"


def build_rows(triples: list, gold: dict) -> list:
    rows = []
    for t in triples:
        prov  = t["provenance"]
        art   = prov["article_id"]
        canon = canonical_from_kg(art)
        deon, src = resolve_deontic(canon, t["predicate_label"], gold)
        rows.append({
            "s_key":    node_key(t["subject_label"], t["subject_uri"], t["subject_typed"]),
            "s_label":  t["subject_label"],
            "s_uri":    t["subject_uri"],
            "s_typed":  t["subject_typed"],
            "o_key":    node_key(t["object_label"], t["object_uri"], t["object_typed"]),
            "o_label":  t["object_label"],
            "o_uri":    t["object_uri"],
            "o_typed":  t["object_typed"],
            "pred":     t["predicate_label"],
            "pred_uri": t["predicate_uri"],
            "reg":      prov["regulation"],
            "art":      art,
            "canon":    canon,
            "chunks":   prov["chunk_ids"],
            "conf":     t["confidence"],
            "deontic":  deon,
            "deon_src": src,
        })
    return rows


CONSTRAINT_CYPHER = """
CREATE CONSTRAINT concept_key IF NOT EXISTS
FOR (c:Concept) REQUIRE c.key IS UNIQUE
"""

# ON MATCH SET so that re-running after a gold update refreshes deontic on
# edges that already exist. Without it, a corrected annotation would never
# reach a graph that had already been loaded.
WRITE_CYPHER = """
UNWIND $rows AS row
MERGE (s:Concept {key: row.s_key})
  ON CREATE SET s.label = row.s_label, s.uri = row.s_uri,
                s.typed = row.s_typed, s.source_reg = row.reg
MERGE (o:Concept {key: row.o_key})
  ON CREATE SET o.label = row.o_label, o.uri = row.o_uri,
                o.typed = row.o_typed, o.source_reg = row.reg
MERGE (s)-[r:REL {predicate: row.pred, article_id: row.art}]->(o)
  ON CREATE SET r.predicate_uri  = row.pred_uri,
                r.regulation     = row.reg,
                r.canonical_id   = row.canon,
                r.chunk_ids      = row.chunks,
                r.confidence     = row.conf,
                r.deontic        = row.deontic,
                r.deontic_source = row.deon_src
  ON MATCH  SET r.canonical_id   = row.canon,
                r.deontic        = row.deontic,
                r.deontic_source = row.deon_src
"""

# Structural characterisation, following Turaga et al. (IEEE Access 2025)
# Table 2: nodes, edges, average degree, density, components.
STATS_CYPHER = """
MATCH (c:Concept)
WITH count(c) AS n
MATCH ()-[r:REL]->()
WITH n, count(r) AS e,
     count(CASE WHEN r.deontic IS NOT NULL THEN 1 END) AS e_deontic,
     count(CASE WHEN r.deontic_source = 'gold' THEN 1 END) AS e_gold
MATCH (t:Concept) WHERE t.typed = true
RETURN n AS nodes, e AS edges, count(t) AS typed_nodes,
       e_deontic AS deontic_edges, e_gold AS gold_sourced_edges,
       toFloat(2*e)/n AS avg_degree,
       toFloat(e)/(n*(n-1)) AS density
"""


def main():
    if not all([URI, USER, PASSWORD]):
        log.error("Missing NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in env")
        return

    gold    = load_gold_deontic(GOLD_PATH)
    triples = json.load(open(TRIPLES_PATH, encoding="utf-8"))
    rows    = build_rows(triples, gold)
    log.info(f"Loaded {len(rows)} triples")

    src = Counter(r["deon_src"] for r in rows)
    deo = Counter(r["deontic"] for r in rows if r["deontic"])
    log.info(f"Deontic source : {dict(src)}")
    log.info(f"Deontic types  : {dict(deo)}")
    if src["predicate"]:
        log.warning(f"{src['predicate']} edges use the predicate fallback — "
                    "these are unverified and cannot express prohibition")
    if src["none"]:
        log.warning(f"{src['none']} edges carry deontic = null")

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        driver.verify_connectivity()
        log.info("Connected to AuraDB")
        with driver.session(database=DATABASE) as session:
            session.run(CONSTRAINT_CYPHER)
            log.info("Constraint ensured on :Concept(key)")

            written = 0
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                session.run(WRITE_CYPHER, rows=batch)
                written += len(batch)
                log.info(f"  wrote {written}/{len(rows)}")

            log.info("--- graph structure ---")
            rec = session.run(STATS_CYPHER).single()
            if rec:
                for k in ("nodes", "edges", "typed_nodes",
                          "deontic_edges", "gold_sourced_edges"):
                    log.info(f"  {k:20} {rec[k]}")
                log.info(f"  {'avg_degree':20} {rec['avg_degree']:.4f}")
                log.info(f"  {'density':20} {rec['density']:.6f}")
        log.info("Done")
    finally:
        driver.close()


if __name__ == "__main__":
    main()