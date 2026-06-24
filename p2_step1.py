import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from rdflib import OWL, RDF, RDFS, Graph, URIRef
from rdflib.namespace import SKOS
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

RDF_PATH   = Path("OUT_CANDIDATES/dpv-fallrisk-ext-v4.rdf")
VOCAB_OUT  = Path("data/vocab_index.json")
EMBED_OUT  = Path("data/class_embeddings.npy")
LOG_OUT    = Path("logs/step1_report.txt")


def load_rdf(path: Path) -> Graph:
    if not path.exists():
        log.error(f"RDF file not found: {path}")
        sys.exit(1)

    g = Graph()
    for fmt in ("xml", "turtle", "n3", "nt"):
        try:
            g.parse(str(path), format=fmt)
            log.info(f"Parsed RDF — format={fmt}, triples={len(g)}")
            return g
        except Exception:
            continue

    log.error("Could not parse RDF with any known format.")
    sys.exit(1)


def best_label(g: Graph, uri: URIRef) -> str:
    for pred in (SKOS.prefLabel, RDFS.label, SKOS.altLabel):
        val = g.value(uri, pred)
        if val:
            return str(val)
    frag = str(uri)
    return frag.split("#")[-1] if "#" in frag else frag.rstrip("/").split("/")[-1]


def extract_classes(g: Graph) -> list[dict]:
    classes, seen = [], set()
    for cls in g.subjects(RDF.type, OWL.Class):
        uri = str(cls)
        if uri in seen or not uri.startswith("http"):
            continue
        seen.add(uri)

        if "dpv#" in uri:
            ns = "dpv"
        elif "/risk#" in uri:
            ns = "dpv-risk"
        elif "/tech#" in uri:
            ns = "dpv-tech"
        else:
            ns = "ext"

        classes.append({
            "uri"    : uri,
            "label"  : best_label(g, cls),
            "comment": str(g.value(cls, RDFS.comment) or "")[:300],
            "ns"     : ns,
        })

    classes.sort(key=lambda x: x["uri"])
    log.info(f"Classes extracted: {len(classes)}")
    return classes


def extract_properties(g: Graph) -> list[dict]:
    props, seen = [], set()
    for prop in g.subjects(RDF.type, OWL.ObjectProperty):
        uri = str(prop)
        if uri in seen or not uri.startswith("http"):
            continue
        seen.add(uri)

        domain = g.value(prop, RDFS.domain)
        rng    = g.value(prop, RDFS.range)

        props.append({
            "uri"   : uri,
            "label" : best_label(g, prop),
            "domain": str(domain) if domain else None,
            "range" : str(rng)    if rng    else None,
        })

    props.sort(key=lambda x: x["uri"])
    log.info(f"Properties extracted: {len(props)}")
    return props


def build_embeddings(classes: list[dict]) -> np.ndarray:
    model  = SentenceTransformer("all-MiniLM-L6-v2")
    texts  = [f"{c['label']} {c['comment']}".strip() for c in classes]
    embeds = model.encode(texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True, convert_to_numpy=True)
    log.info(f"Embeddings shape: {embeds.shape}")
    return embeds.astype(np.float32)


def validate(classes: list[dict], props: list[dict]) -> list[str]:
    warnings = []
    if len(classes) < 500:
        warnings.append(f"Low class count: {len(classes)}, expected ~627")
    if len(props) < 10:
        warnings.append(f"Low property count: {len(props)}, expected 13")
    no_label = [c for c in classes if not c["label"].strip()]
    if no_label:
        warnings.append(f"{len(no_label)} classes have empty labels")
    missing_dr = [p for p in props if not p["domain"] or not p["range"]]
    if missing_dr:
        warnings.append(f"{len(missing_dr)} properties missing domain/range: {[p['label'] for p in missing_dr]}")
    return warnings


def write_report(classes: list[dict], props: list[dict], warnings: list[str]) -> None:
    LOG_OUT.parent.mkdir(parents=True, exist_ok=True)
    ns_counts: dict[str, int] = {}
    for c in classes:
        ns_counts[c["ns"]] = ns_counts.get(c["ns"], 0) + 1

    lines = [
        f"Step 1 Report — {datetime.now().isoformat(timespec='seconds')}",
        f"Classes: {len(classes)}  |  Properties: {len(props)}",
        "",
        "Namespace breakdown:",
    ]
    for ns, cnt in sorted(ns_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {ns:<12}  {cnt}")

    lines += ["", "Object properties:"]
    for p in props:
        lines.append(f"  {p['label']:<40}  {p['uri']}")
        if p["domain"]: lines.append(f"    domain → {p['domain']}")
        if p["range"]:  lines.append(f"    range  → {p['range']}")

    lines += ["", "Warnings:"]
    lines += [f"  ⚠  {w}" for w in warnings] if warnings else ["  ✅  All checks passed"]

    LOG_OUT.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Report → {LOG_OUT}")


def main():
    Path("data").mkdir(parents=True, exist_ok=True)

    g       = load_rdf(RDF_PATH)
    classes = extract_classes(g)
    props   = extract_properties(g)

    warnings = validate(classes, props)
    for w in warnings:
        log.warning(w)
    if not warnings:
        log.info("All validation checks passed")

    embeddings = build_embeddings(classes)

    vocab = {
        "meta": {
            "rdf_source"    : str(RDF_PATH),
            "num_classes"   : len(classes),
            "num_properties": len(props),
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dim" : int(embeddings.shape[1]),
            "created_at"    : datetime.now().isoformat(timespec="seconds"),
        },
        "classes"   : classes,
        "properties": props,
    }

    with open(VOCAB_OUT, "w", encoding="utf-8") as f:
        json.dump(vocab, f, indent=2, ensure_ascii=False)
    log.info(f"Vocabulary → {VOCAB_OUT}")

    np.save(str(EMBED_OUT), embeddings)
    log.info(f"Embeddings → {EMBED_OUT}")

    write_report(classes, props, warnings)

    print(f"\nClasses: {len(classes)}  |  Properties: {len(props)}  |  Embeddings: {embeddings.shape}")
    print(f"Next → step2_semantic_retrieval.py")


if __name__ == "__main__":
    main()