# """
# Step 5 - AuraDB Population
# Loads clean_triples.json into Neo4j AuraDB.

# Schema:
#   (:Concept {key, label, uri, typed, source_reg})
#      -[:REL {predicate, predicate_uri, regulation, article_id, chunk_ids, confidence}]->
#   (:Concept {...})

# Node identity (MERGE key):
#   typed node  -> key = uri        (deduplicates across articles)
#   new node    -> key = "new:" + label

# Idempotent: re-running won't duplicate (MERGE on key + edge signature).
# Batched in groups of 50. Resumable — MERGE means partial runs are safe to re-run.


import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)
logging.getLogger("neo4j").setLevel(logging.WARNING)

TRIPLES_PATH = Path("data/clean_triples.json")
BATCH_SIZE   = 50

URI      = os.getenv("NEO4J_URI")
USER     = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def node_key(label: str, uri, typed: bool) -> str:
    return uri if (typed and uri) else f"new:{label}"


def build_rows(triples: list[dict]) -> list[dict]:
    rows = []
    for t in triples:
        rows.append({
            "s_key"  : node_key(t["subject_label"], t["subject_uri"], t["subject_typed"]),
            "s_label": t["subject_label"],
            "s_uri"  : t["subject_uri"],
            "s_typed": t["subject_typed"],
            "o_key"  : node_key(t["object_label"], t["object_uri"], t["object_typed"]),
            "o_label": t["object_label"],
            "o_uri"  : t["object_uri"],
            "o_typed": t["object_typed"],
            "pred"   : t["predicate_label"],
            "pred_uri": t["predicate_uri"],
            "reg"    : t["provenance"]["regulation"],
            "art"    : t["provenance"]["article_id"],
            "chunks" : t["provenance"]["chunk_ids"],
            "conf"   : t["confidence"],
        })
    return rows


CONSTRAINT_CYPHER = """
CREATE CONSTRAINT concept_key IF NOT EXISTS
FOR (c:Concept) REQUIRE c.key IS UNIQUE
"""

WRITE_CYPHER = """
UNWIND $rows AS row
MERGE (s:Concept {key: row.s_key})
  ON CREATE SET s.label = row.s_label, s.uri = row.s_uri,
                s.typed = row.s_typed, s.source_reg = row.reg
MERGE (o:Concept {key: row.o_key})
  ON CREATE SET o.label = row.o_label, o.uri = row.o_uri,
                o.typed = row.o_typed, o.source_reg = row.reg
MERGE (s)-[r:REL {predicate: row.pred, article_id: row.art}]->(o)
  ON CREATE SET r.predicate_uri = row.pred_uri,
                r.regulation    = row.reg,
                r.chunk_ids     = row.chunks,
                r.confidence    = row.conf
"""


def main():
    if not all([URI, USER, PASSWORD]):
        log.error("Missing NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in env")
        return

    with open(TRIPLES_PATH, encoding="utf-8") as f:
        triples = json.load(f)

    rows = build_rows(triples)
    log.info(f"Loaded {len(rows)} triples")

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
                log.info(f"  Written {written}/{len(rows)}")

        # Verify
        with driver.session(database=DATABASE) as session:
            node_count = session.run("MATCH (c:Concept) RETURN count(c) AS n").single()["n"]
            edge_count = session.run("MATCH ()-[r:REL]->() RETURN count(r) AS n").single()["n"]
            typed_count = session.run("MATCH (c:Concept {typed: true}) RETURN count(c) AS n").single()["n"]

        print(f"\nNodes in graph   : {node_count}")
        print(f"  typed          : {typed_count}")
        print(f"  new            : {node_count - typed_count}")
        print(f"Edges in graph   : {edge_count}")
        print("Next -> step6_graph_validation.py")

    finally:
        driver.close()


if __name__ == "__main__":
    main()