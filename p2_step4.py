"""
Step 4 — Reconciliation, Sanitization & Validation
===================================================
Takes raw extracted triples and prepares them for Neo4j:

  1. RECONCILE  — promote NEW nodes that exactly match a vocab class to typed
  2. SANITIZE   — make every node label Neo4j-safe (no apostrophes, no leading digit)
  3. VALIDATE   — soft domain/range check against property constraints (warn, don't reject)
  4. REPORT     — before/after stats

Input : data/validated_triples.json   (Step 3 output)
        data/vocab_index.json
Output: data/clean_triples.json        (ready for Step 5 AuraDB load)
        logs/step4_report.txt
"""

import json
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

TRIPLES_PATH = Path("data/validated_triples.json")
VOCAB_PATH   = Path("data/vocab_index.json")
OUTPUT_PATH  = Path("data/clean_triples.json")
REPORT_PATH  = Path("logs/step4_report.txt")


def norm(s: str) -> str:
    return s.lower().replace(" ", "").replace("_", "").replace("-", "")


def sanitize_label(label: str) -> str:
    """
    Make a node label safe to use as a Neo4j node identity.
    - strip apostrophes and quotes
    - remove characters that aren't alphanumeric
    - prefix with N_ if it starts with a digit
    """
    cleaned = re.sub(r"['\"]", "", label)
    cleaned = re.sub(r"[^A-Za-z0-9]", "", cleaned)
    if cleaned and cleaned[0].isdigit():
        cleaned = "N_" + cleaned
    return cleaned or "Unknown"


def reconcile_node(label: str, typed: bool, uri, vocab_norm: dict):
    """
    If a NEW node exactly matches a vocab class, promote it to typed.
    Returns (label, uri, typed, promoted_flag).
    """
    if typed:
        return label, uri, True, False

    match = vocab_norm.get(norm(label))
    if match:
        return match["name"], match["uri"], True, True

    return label, None, False, False


def soft_domain_range_check(triple: dict, prop_constraints: dict) -> str | None:
    """
    Soft check: if subject/object are typed and clearly violate the property's
    declared domain/range, return a warning string. Never rejects.
    """
    pred = triple["predicate_label"]
    constraint = prop_constraints.get(pred)
    if not constraint:
        return None

    warnings = []
    # Only check when the node is typed (we know its real class name)
    if triple["subject_typed"]:
        exp = constraint["domain"]
        got = triple["subject_label"]
        if exp and norm(exp) != norm(got):
            # only flag for the 14 base classes — ext subclasses can't be verified
            if got in BASE_CLASSES and norm(got) != norm(exp):
                warnings.append(f"domain expected {exp}, got {got}")

    if triple["object_typed"]:
        exp = constraint["range"]
        got = triple["object_label"]
        if exp and norm(exp) != norm(got):
            if got in BASE_CLASSES and norm(got) != norm(exp):
                warnings.append(f"range expected {exp}, got {got}")

    return "; ".join(warnings) if warnings else None


BASE_CLASSES = {
    "Processing", "PersonalData", "DataSubject", "DataController",
    "LegalBasis", "Consent", "Purpose", "Right", "Obligation", "Risk",
    "TechnicalMeasure", "OrganisationalMeasure", "Notice", "Entity",
    "TechnicalOrganisationalMeasure", "RiskAssessment",
}


def main():
    with open(TRIPLES_PATH, encoding="utf-8") as f:
        triples = json.load(f)
    with open(VOCAB_PATH, encoding="utf-8") as f:
        vocab = json.load(f)

    vocab_norm = {norm(c["name"]): c for c in vocab["classes"]}
    prop_constraints = {
        p["label"]: {
            "domain": p["domain"].split("#")[-1] if p["domain"] else None,
            "range" : p["range"].split("#")[-1]  if p["range"]  else None,
        }
        for p in vocab["properties"]
    }

    # Stats before
    nodes_before = len(triples) * 2
    typed_before = sum((t["subject_typed"] + t["object_typed"]) for t in triples)

    promoted_count = 0
    sanitized_count = 0
    dr_warnings = []

    clean = []
    for t in triples:
        # 1. Reconcile
        s_lbl, s_uri, s_typed, s_promo = reconcile_node(
            t["subject_label"], t["subject_typed"], t["subject_uri"], vocab_norm)
        o_lbl, o_uri, o_typed, o_promo = reconcile_node(
            t["object_label"], t["object_typed"], t["object_uri"], vocab_norm)
        promoted_count += s_promo + o_promo

        # 2. Sanitize
        s_clean = sanitize_label(s_lbl)
        o_clean = sanitize_label(o_lbl)
        if s_clean != s_lbl: sanitized_count += 1
        if o_clean != o_lbl: sanitized_count += 1

        new_t = {
            "subject_label"  : s_clean,
            "subject_uri"    : s_uri,
            "subject_typed"  : s_typed,
            "predicate_label": t["predicate_label"],
            "predicate_uri"  : t["predicate_uri"],
            "object_label"   : o_clean,
            "object_uri"     : o_uri,
            "object_typed"   : o_typed,
            "confidence"     : t["confidence"],
            "provenance"     : t["provenance"],
        }

        # 3. Soft domain/range check
        w = soft_domain_range_check(new_t, prop_constraints)
        if w:
            dr_warnings.append(f"{s_clean} --{t['predicate_label']}--> {o_clean}: {w}")

        clean.append(new_t)

    # Stats after
    typed_after = sum((t["subject_typed"] + t["object_typed"]) for t in clean)
    fully_before = sum(1 for t in triples if t["subject_typed"] and t["object_typed"])
    fully_after  = sum(1 for t in clean   if t["subject_typed"] and t["object_typed"])

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)

    # Report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Step 4 — Reconciliation & Validation Report",
        "=" * 50,
        f"Triples processed     : {len(clean)}",
        "",
        "Node-level typing:",
        f"  Before              : {typed_before}/{nodes_before}  ({100*typed_before//nodes_before}%)",
        f"  After reconcile     : {typed_after}/{nodes_before}  ({100*typed_after//nodes_before}%)",
        f"  Nodes promoted      : {promoted_count}",
        "",
        "Fully-typed triples (both subject+object):",
        f"  Before              : {fully_before}  ({100*fully_before//len(triples)}%)",
        f"  After               : {fully_after}  ({100*fully_after//len(clean)}%)",
        "",
        f"Labels sanitized      : {sanitized_count}",
        f"Domain/range warnings : {len(dr_warnings)}",
    ]
    if dr_warnings:
        lines += ["", "Domain/range mismatches (informational, not rejected):"]
        lines += [f"  ⚠ {w}" for w in dr_warnings[:30]]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    log.info(f"Promoted {promoted_count} nodes to typed")
    log.info(f"Sanitized {sanitized_count} labels")
    log.info(f"Node typing: {100*typed_before//nodes_before}% → {100*typed_after//nodes_before}%")
    log.info(f"Clean triples → {OUTPUT_PATH}")
    log.info(f"Report → {REPORT_PATH}")

    print(f"\nTriples       : {len(clean)}")
    print(f"Node typing   : {100*typed_before//nodes_before}% → {100*typed_after//nodes_before}%")
    print(f"Fully-typed   : {100*fully_before//len(triples)}% → {100*fully_after//len(clean)}%")
    print(f"Sanitized     : {sanitized_count}")
    print(f"Output        : {OUTPUT_PATH}")
    print("Next → step5_auradb_load.py")


if __name__ == "__main__":
    main()