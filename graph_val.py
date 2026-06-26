"""
Step 6 — Graph Validation
=========================
Runs a suite of validation queries against AuraDB and reports results.
Covers: structure, coverage, provenance, connectivity, cross-regulation.
"""

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

REPORT_PATH = Path("logs/step6_validation_report.txt")

URI      = os.getenv("NEO4J_URI")
USER     = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

CHECKS = [
    {
        "name"    : "Total nodes and edges",
        "cypher"  : "MATCH (c:Concept) WITH count(c) AS nodes MATCH ()-[r:REL]->() RETURN nodes, count(r) AS edges",
        "expect"  : "nodes=546, edges=618",
        "level"   : "BASIC",
    },
    {
        "name"    : "Typed vs new node breakdown",
        "cypher"  : "MATCH (c:Concept) RETURN c.typed AS typed, count(c) AS n ORDER BY typed DESC",
        "expect"  : "true: 204, false: 342",
        "level"   : "BASIC",
    },
    {
        "name"    : "Triples per regulation",
        "cypher"  : "MATCH ()-[r:REL]->() RETURN r.regulation AS regulation, count(r) AS triples ORDER BY triples DESC",
        "expect"  : "EU AI Act ~225, GDPR ~144, UK MDR ~106, EU MDR ~96, DUAA ~47",
        "level"   : "BASIC",
    },
    {
        "name"    : "Predicate distribution",
        "cypher"  : "MATCH ()-[r:REL]->() RETURN r.predicate AS predicate, count(r) AS n ORDER BY n DESC",
        "expect"  : "hasObligation most frequent (~187), all 13 predicates present",
        "level"   : "BASIC",
    },
    {
        "name"    : "Orphan nodes (no edges)",
        "cypher"  : "MATCH (c:Concept) WHERE NOT (c)--() RETURN count(c) AS orphans",
        "expect"  : "0  (every node should have at least one edge)",
        "level"   : "BASIC",
    },
    {
        "name"    : "Nodes missing required properties",
        "cypher"  : "MATCH (c:Concept) WHERE c.label IS NULL OR c.key IS NULL RETURN count(c) AS broken",
        "expect"  : "0",
        "level"   : "BASIC",
    },
    {
        "name"    : "Known triple — DataSubject has right to withdraw consent (GDPR Art7)",
        "cypher"  : """MATCH (s:Concept)-[r:REL]->(o:Concept)
                       WHERE s.label = 'DataSubject'
                         AND r.predicate = 'hasRight'
                         AND o.label = 'RightToWithdrawConsent'
                       RETURN s.label, r.predicate, o.label, r.regulation, r.article_id""",
        "expect"  : "1 row: DataSubject hasRight RightToWithdrawConsent, GDPR, GDPR__Art7",
        "level"   : "MEDIUM",
    },
    {
        "name"    : "Known triple — Processing has legal basis (GDPR Art6)",
        "cypher"  : """MATCH (s:Concept)-[r:REL]->(o:Concept)
                       WHERE s.label = 'Processing'
                         AND r.predicate = 'hasLegalBasis'
                         AND r.article_id = 'GDPR__Art6'
                       RETURN s.label, r.predicate, o.label, r.confidence ORDER BY r.confidence DESC""",
        "expect"  : "Multiple rows — Consent, ContractNecessity, LegalObligationUnionLaw, VitalInterest etc",
        "level"   : "MEDIUM",
    },
    {
        "name"    : "Top 10 most connected nodes (hubs)",
        "cypher"  : """MATCH (c:Concept)-[r:REL]-()
                       RETURN c.label AS concept, c.typed AS typed, count(r) AS degree
                       ORDER BY degree DESC LIMIT 10""",
        "expect"  : "Entity, Processing, PersonalData should be top hubs",
        "level"   : "MEDIUM",
    },
    {
        "name"    : "Provenance — all triples from GDPR Art9 with chunk IDs",
        "cypher"  : """MATCH (s:Concept)-[r:REL]->(o:Concept)
                       WHERE r.article_id = 'GDPR__Art9'
                       RETURN s.label, r.predicate, o.label, r.chunk_ids, r.confidence
                       ORDER BY r.confidence DESC""",
        "expect"  : "~9 triples, all with chunk_ids like ['GDPR_Art9_Para1', ...]",
        "level"   : "MEDIUM",
    },
    {
        "name"    : "Cross-regulation concepts (appear in 3+ regulations)",
        "cypher"  : """MATCH (c:Concept)-[r:REL]-()
                       WITH c, collect(DISTINCT r.regulation) AS regs
                       WHERE size(regs) >= 3
                       RETURN c.label, c.typed, regs ORDER BY size(regs) DESC""",
        "expect"  : "Base concepts like Entity, Processing, Obligation should span all regulations",
        "level"   : "MEDIUM",
    },
    {
        "name"    : "Edges missing provenance properties",
        "cypher"  : """MATCH ()-[r:REL]->()
                       WHERE r.regulation IS NULL OR r.article_id IS NULL OR r.confidence IS NULL
                       RETURN count(r) AS broken""",
        "expect"  : "0  (every edge must have full provenance)",
        "level"   : "MEDIUM",
    },
    {
        "name"    : "Two-hop path — PersonalData risk chain",
        "cypher"  : """MATCH path = (s:Concept {label:'PersonalData'})-[:REL*2]->(end:Concept)
                       WHERE end.label <> 'PersonalData'
                       RETURN [n IN nodes(path) | n.label] AS chain,
                              [r IN relationships(path) | r.predicate] AS predicates
                       LIMIT 10""",
        "expect"  : "Paths showing PersonalData -> Risk/Obligation -> mitigation classes",
        "level"   : "EXTREME",
    },
    {
        "name"    : "Cross-regulation compliance — obligations shared by GDPR and EU AI Act",
        "cypher"  : """MATCH (s1:Concept)-[r1:REL {predicate:'hasObligation', regulation:'GDPR'}]->(o:Concept)
                       MATCH (s2:Concept)-[r2:REL {predicate:'hasObligation', regulation:'EU AI Act'}]->(o)
                       RETURN DISTINCT o.label AS shared_obligation, o.typed
                       ORDER BY o.label""",
        "expect"  : "Obligations like Obligation, Notice, TechnicalOrganisationalMeasure shared across both",
        "level"   : "EXTREME",
    },
    {
        "name"    : "Subgraph density — typed-only nodes and edges",
        "cypher"  : """MATCH (s:Concept {typed:true})-[r:REL]->(o:Concept {typed:true})
                       RETURN count(DISTINCT s) + count(DISTINCT o) AS typed_nodes,
                              count(r) AS typed_edges""",
        "expect"  : "typed_edges ~200 (fully-typed triples from Step 4)",
        "level"   : "EXTREME",
    },
    {
        "name"    : "Full provenance chain — trace GDPR Art5 obligations back to chunks",
        "cypher"  : """MATCH (s:Concept)-[r:REL]->(o:Concept)
                       WHERE r.article_id = 'GDPR__Art5'
                       RETURN s.label, r.predicate, o.label,
                              r.chunk_ids[0] AS first_chunk, r.confidence
                       ORDER BY r.confidence DESC""",
        "expect"  : "~11 triples, chunk_ids starting with 'GDPR_Art5_Para1_*'",
        "level"   : "EXTREME",
    },
]


def run_checks(session) -> list[dict]:
    results = []
    for check in CHECKS:
        try:
            rows = session.run(check["cypher"]).data()
            results.append({
                "name"   : check["name"],
                "level"  : check["level"],
                "expect" : check["expect"],
                "rows"   : rows,
                "status" : "OK",
            })
            log.info(f"[{check['level']}] {check['name']} → {len(rows)} row(s)")
        except Exception as e:
            results.append({
                "name"  : check["name"],
                "level" : check["level"],
                "expect": check["expect"],
                "rows"  : [],
                "status": f"ERROR: {e}",
            })
            log.error(f"[{check['level']}] {check['name']} → {e}")
    return results


def write_report(results: list[dict]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Step 6 — Graph Validation Report", "=" * 60, ""]

    for level in ("BASIC", "MEDIUM", "EXTREME"):
        lines.append(f"── {level} ──")
        for r in [x for x in results if x["level"] == level]:
            lines.append(f"\n  {r['name']}")
            lines.append(f"  Expected : {r['expect']}")
            lines.append(f"  Status   : {r['status']}")
            for row in r["rows"][:5]:
                lines.append(f"    {row}")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Report → {REPORT_PATH}")


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        driver.verify_connectivity()
        log.info("Connected to AuraDB")

        with driver.session(database=DATABASE) as session:
            results = run_checks(session)

        write_report(results)

        passed = sum(1 for r in results if r["status"] == "OK")
        failed = len(results) - passed
        print(f"\nChecks passed : {passed}/{len(results)}")
        print(f"Checks failed : {failed}")
        print(f"Report        : {REPORT_PATH}")
        if failed:
            print("\nFailed checks:")
            for r in results:
                if r["status"] != "OK":
                    print(f"  ✗ {r['name']}: {r['status']}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()