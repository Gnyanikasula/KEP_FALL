"""
phase1_llm_restrictions.py  -  v3 -> v4  (LLM restriction pass)


What this does:
  1. Loads DPV + v3 ontology
  2. Finds all KEP classes that have NO someValuesFrom restriction
  3. Groups them by source_chunk_id (one LLM call per chunk, not per class)
  4. For each chunk group: sends chunk text + class names + allowed vocabulary
     to Groq and asks ONLY for OWL property restrictions
  5. Validates every returned restriction:
       - class must exist in ontology
       - property must be one of the 13 declared DPV properties
       - target must exist in ontology (KEP or DPV)
  6. Applies validated restrictions via owlready2
  7. Runs HermiT - exits on any unsatisfiable class
  8. Serializes clean output -> v4 (same filter as phase1_fix.py)


Input:
  OUT_CANDIDATES/dpv-fallrisk-ext-v3.rdf
  OUT_CANDIDATES/classes_created.json      (source_chunk_id per class)
  regulatory_chunks.json                   (chunk text)

Output:
  OUT_CANDIDATES/dpv-fallrisk-ext-v4.rdf
  OUT_CANDIDATES/llm_restrictions_log.md
  OUT_CANDIDATES/llm_restrictions_raw.json  (all LLM responses for reproducibility)
"""

import os
import sys
import re
import json
import time
import types

import rdflib
from rdflib import Graph, RDF, OWL, RDFS, Namespace, URIRef, BNode, Literal
from owlready2 import (
    get_ontology, default_world, Thing,
    sync_reasoner_hermit, IRIS, ObjectProperty,
)
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# paths

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DPV_BASE      = os.environ.get("DPV_BASE", r"D:\dpv-2.2.1")
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
OUT_DIR       = os.path.join(BASE_DIR, "OUT_CANDIDATES")

IN_V3         = os.path.join(OUT_DIR, "dpv-fallrisk-ext-v3.rdf")
CLASSES_JSON  = os.path.join(OUT_DIR, "classes_created.json")
CHUNKS_JSON   = os.path.join(BASE_DIR, "regulatory_chunks.json")

OUT_V4        = os.path.join(OUT_DIR, "dpv-fallrisk-ext-v4.rdf")
OUT_LOG       = os.path.join(OUT_DIR, "llm_restrictions_log.md")
OUT_RAW       = os.path.join(OUT_DIR, "llm_restrictions_raw.json")

FALLRISK_NS   = "https://w3id.org/kep/fallrisk#"
DPV_NS        = "https://w3id.org/dpv/owl#"
DPV_RISK_NS   = "https://w3id.org/dpv/risk/owl#"
DPV_GDPR_NS   = "https://w3id.org/dpv/legal/eu/gdpr/owl#"
DPV_PD_NS     = "https://w3id.org/dpv/pd/owl#"
DPV_AI_NS     = "https://w3id.org/dpv/ai/owl#"
DPV_AIACT_NS  = "https://w3id.org/dpv/legal/eu/aiact/owl#"

DPV_MODULES = [
    os.path.join(DPV_BASE, "dpv",   "dpv-owl.rdf"),
    os.path.join(DPV_BASE, "pd",    "pd-owl.rdf"),
    os.path.join(DPV_BASE, "risk",  "risk-owl.rdf"),
    os.path.join(DPV_BASE, "ai",    "ai-owl.rdf"),
    os.path.join(DPV_BASE, "legal", "eu", "gdpr",   "eu-gdpr-owl.rdf"),
    os.path.join(DPV_BASE, "legal", "eu", "aiact",  "eu-aiact-owl.rdf"),
]

MODEL         = "meta-llama/llama-4-scout-17b-16e-instruct"
MAX_TOKENS    = 900
REQUEST_DELAY = 2.2
MAX_RETRIES   = 5
RETRY_BASE    = 15.0

# The 13 allowed DPV properties - must match phase1_fix.py exactly.
# Local name -> full URI.  LLM is shown local names; validation uses full URIs.
ALLOWED_PROPERTIES = {
    "hasPersonalData":                DPV_NS      + "hasPersonalData",
    "hasOrganisationalMeasure":       DPV_NS      + "hasOrganisationalMeasure",
    "hasTechnicalOrganisationalMeasure": DPV_NS   + "hasTechnicalOrganisationalMeasure",
    "hasRiskAssessment":              DPV_RISK_NS + "hasRiskAssessment",
    "hasLegalBasis":                  DPV_NS      + "hasLegalBasis",
    "hasPurpose":                     DPV_NS      + "hasPurpose",
    "hasDataSubject":                 DPV_NS      + "hasDataSubject",
    "hasRight":                       DPV_NS      + "hasRight",
    "hasObligation":                  DPV_NS      + "hasObligation",
    "hasTechnicalMeasure":            DPV_NS      + "hasTechnicalMeasure",
    "hasNotice":                      DPV_NS      + "hasNotice",
    "hasRisk":                        DPV_NS      + "hasRisk",
    "isMitigatedByMeasure":           DPV_NS      + "isMitigatedByMeasure",
}

# LLM Prompt

SYSTEM_PROMPT = """\
You are an OWL ontology engineer.
Your ONLY task is to identify owl:someValuesFrom restrictions for existing classes.
Do NOT suggest new classes. Do NOT rename classes. Do NOT explain anything.

You are given:
  - A regulatory text chunk (breadcrumb header + text)
  - A list of OWL classes that were extracted from this chunk
  - 13 allowed DPV object properties (you may ONLY use these)
  - A sample of allowed target classes (you may ONLY use these)

Rules:
  1. A restriction is only valid if it is EXPLICITLY supported by the regulatory text.
  2. Use ONLY property names from the allowed list - no others.
  3. Use ONLY class names from the allowed targets - no others.
  4. If a class already has the restriction, do NOT repeat it.
  5. If no restriction is warranted, return [].
  6. Output ONLY a valid JSON array - no markdown, no explanation.

Schema:
[
  {
    "class": "ExistingClassName",
    "property": "hasLegalBasis",
    "target": "ExistingTargetClass",
    "rationale": "One sentence citing the specific text that justifies this."
  }
]
"""

REPAIR_PROMPT = """\
Convert the text below into a valid JSON array matching this schema:
[{"class": "ClassName", "property": "propertyName",
  "target": "TargetClass", "rationale": "one sentence"}]
Output ONLY JSON. No markdown. No explanation.
"""


# helpers

def local(uri: str) -> str:
    return uri.split("#")[-1] if "#" in uri else uri.split("/")[-1]


def parse_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw.strip())


def call_llm(client, messages):
    delay = RETRY_BASE
    for attempt in range(MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = client.chat.completions.create(
                model=MODEL, max_tokens=MAX_TOKENS, messages=messages)
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            if attempt < MAX_RETRIES and any(
                    k in err for k in ("rate_limit", "429", "too many")):
                m = re.search(r"try again in ([0-9.]+)s", err)
                wait = float(m.group(1)) + 2.0 if m else delay
                print(f"    rate-limit, waiting {wait:.0f}s …")
                time.sleep(wait)
                delay *= 2
            else:
                raise


def load_dpv():
    print("Loading DPV modules …")
    for p in DPV_MODULES:
        if not os.path.exists(p):
            sys.exit(f"DPV module not found: {p}")
        get_ontology(p).load()
    total = len(list(default_world.classes()))
    print(f"  {total} DPV classes\n")
    return {c.name: c for c in default_world.classes()}


# step 1 - load v3 into owlready2

def load_v3(all_dpv):
    """
    Rebuild the v3 ontology in owlready2 from the RDF file.
    Returns (onto, new_classes, existing_restrictions)
    existing_restrictions: dict  class_local -> set of (prop_uri, target_uri)
    """
    print("Loading v3 RDF …")
    g = Graph()
    g.parse(IN_V3)

    onto = get_ontology(FALLRISK_NS)
    new_classes = {}

    # read class + parent + label/comment from rdflib
    class_data = {}
    for subj in g.subjects(RDF.type, OWL.Class):
        if not str(subj).startswith(FALLRISK_NS):
            continue
        name = local(str(subj))
        parents = [o for o in g.objects(subj, RDFS.subClassOf)
                   if not isinstance(o, BNode)]
        labels   = list(g.objects(subj, RDFS.label))
        comments = list(g.objects(subj, RDFS.comment))
        class_data[name] = {
            "parent_uri": str(parents[0]) if parents else None,
            "label":      str(labels[0])   if labels   else name,
            "comment":    str(comments[0]) if comments else "",
        }

    # read existing restrictions so we don't duplicate them
    existing_restrictions: dict[str, set] = {}
    for bnode in g.subjects(RDF.type, OWL.Restriction):
        props   = list(g.objects(bnode, OWL.onProperty))
        targets = list(g.objects(bnode, OWL.someValuesFrom))
        parents = list(g.subjects(RDFS.subClassOf, bnode))
        if not (props and targets and parents):
            continue
        cls_uri = str(parents[0])
        if not cls_uri.startswith(FALLRISK_NS):
            continue
        cls_local = local(cls_uri)
        if cls_local not in existing_restrictions:
            existing_restrictions[cls_local] = set()
        existing_restrictions[cls_local].add(
            (str(props[0]), str(targets[0]))
        )

    # pass 1 - create all classes with Thing
    with onto:
        for name, info in class_data.items():
            cls = types.new_class(name, (Thing,))
            cls.label   = [info["label"]]
            cls.comment = [info["comment"]]
            new_classes[name] = cls

    # pass 2 - set parents
    fixed = 0
    for name, info in class_data.items():
        p_uri = info["parent_uri"]
        if not p_uri or p_uri.endswith("#Thing"):
            continue
        p_local = local(p_uri)
        parent_cls = all_dpv.get(p_local) or new_classes.get(p_local) or IRIS[p_uri]
        if parent_cls is None:
            continue
        new_classes[name].is_a = [parent_cls]
        fixed += 1

    # re-apply existing restrictions so owlready2 knows about them
    with onto:
        for cls_local, rest_set in existing_restrictions.items():
            cls = new_classes.get(cls_local)
            if cls is None:
                continue
            for prop_uri, target_uri in rest_set:
                prop = IRIS[prop_uri]
                tgt  = IRIS[target_uri] or all_dpv.get(local(target_uri))
                if prop and tgt:
                    cls.is_a.append(prop.some(tgt))

    n_existing = sum(len(v) for v in existing_restrictions.values())
    print(f"  {len(new_classes)} classes loaded  |  "
          f"{fixed} parented  |  {n_existing} existing restrictions\n")
    return onto, new_classes, existing_restrictions


# step 2 - find classes without restrictions + group by chunk

def find_unrestricted(new_classes, existing_restrictions, classes_json_path):
    """
    Returns dict: chunk_id -> list of class local names without restrictions.
    Skips classes not in classes_created.json (domain classes added in fix step).
    """
    print("Finding classes without restrictions …")
    with open(classes_json_path, encoding="utf-8") as f:
        classes_data = json.load(f)

    chunk_to_classes: dict[str, list] = {}
    for entry in classes_data:
        name = entry.get("name")
        if not name or entry.get("merged_into"):
            continue
        if name not in new_classes:
            continue
        if name in existing_restrictions:
            continue  # already has at least one restriction
        chunk_id = entry.get("source_chunk_id", "unknown")
        if chunk_id not in chunk_to_classes:
            chunk_to_classes[chunk_id] = []
        chunk_to_classes[chunk_id].append(name)

    total_classes = sum(len(v) for v in chunk_to_classes.values())
    print(f"  {total_classes} classes without restrictions "
          f"across {len(chunk_to_classes)} chunks\n")
    return chunk_to_classes


# step 3 - LLM restriction extraction


def build_allowed_targets(new_classes, all_dpv):
    """
    Build set of valid target class local names for validation.
    Includes KEP classes + DPV classes referenced as parents.
    """
    valid = set(new_classes.keys())
    valid.update(all_dpv.keys())
    return valid


def build_target_sample(new_classes):
    """
    Build a representative sample of target classes to include in the prompt.
    Full list is too large - we give a meaningful subset + note that others exist.
    Prioritise classes most likely to be useful as restriction targets.
    """
    priority_targets = [
        # personal data
        "HealthData", "SpecialCategoryPersonalData", "PersonalData",
        "BiometricData", "GeneticData",
        # legal basis
        "LegalBasis", "Consent", "LegitimateInterest", "LegalObligation",
        "VitalInterests", "PublicInterest",
        # measures
        "HumanInvolvementForOversight", "DataSecurityManagement",
        "PrivacyByDesign", "PrivacyByDefault",
        # risk
        "RiskAssessment", "RiskManagementSystem", "DataProtectionImpactAssessment",
        # rights
        "Right", "RightToAccess", "RightToErasure", "RightToRectification",
        # obligations
        "Obligation", "TransparencyObligation",
        # domain
        "FallRiskPrediction", "FallRiskScore", "AccelerometerReading",
        "GaitAnalysisOutput", "WearableSensor", "WearableDataProcessing",
        # AI Act specific
        "HighRiskAISystem", "HumanOversight", "ConformityAssessment",
        # MDR specific
        "MedicalDeviceClassification", "ClinicalEvaluation",
    ]
    # include priority targets that actually exist, then pad with KEP classes
    sample = [t for t in priority_targets
              if t in new_classes or t in {"HealthData", "SpecialCategoryPersonalData",
                                           "HumanInvolvementForOversight",
                                           "DataSecurityManagement",
                                           "PrivacyByDesign", "PrivacyByDefault",
                                           "RiskAssessment"}]
    # add remaining KEP classes (up to 150 total)
    remaining = [n for n in new_classes if n not in sample]
    sample.extend(remaining[: max(0, 150 - len(sample))])
    return sample


def extract_restrictions_for_chunk(
        client, chunk, class_names, allowed_targets_sample, raw_log):
    """
    One LLM call for all classes from a single chunk.
    Returns list of validated raw dicts [{class, property, target, rationale}].
    """
    prop_list    = ", ".join(ALLOWED_PROPERTIES.keys())
    target_list  = ", ".join(allowed_targets_sample)
    class_list   = ", ".join(class_names)

    user_msg = (
        f"Breadcrumb: {chunk.get('context_header', '')}\n"
        f"Text:\n{chunk['text']}\n\n"
        f"Classes extracted from this chunk:\n{class_list}\n\n"
        f"Allowed properties (use ONLY these):\n{prop_list}\n\n"
        f"Allowed target classes (use ONLY these; others exist but use only known ones):\n"
        f"{target_list}\n\n"
        f"Existing restrictions to avoid duplicating: none of these classes "
        f"have any restrictions yet.\n\n"
        f"Return ONLY a JSON array. If no restrictions are justified, return []."
    )

    raw = ""
    try:
        raw = call_llm(client, [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ])
        raw_log.append({"chunk_id": chunk["chunk_id"],
                        "classes": class_names, "raw": raw})
        try:
            return parse_json(raw)
        except Exception:
            # attempt repair
            repair_raw = call_llm(client, [
                {"role": "system", "content": REPAIR_PROMPT},
                {"role": "user",   "content": raw},
            ])
            raw_log[-1]["repair_raw"] = repair_raw
            return parse_json(repair_raw)
    except Exception as e:
        print(f"    [fail] chunk {chunk['chunk_id']}: {e}")
        raw_log.append({"chunk_id": chunk["chunk_id"],
                        "classes": class_names, "raw": raw, "error": str(e)})
        return []


# step 4 - validate + apply restrictions

def validate_and_apply(
        llm_results, onto, new_classes, all_dpv,
        existing_restrictions, valid_targets):
    """
    Validates every LLM-returned restriction:
      - class must exist in ontology
      - property must be in ALLOWED_PROPERTIES
      - target must exist in valid_targets (KEP or DPV)
    Applies validated restrictions via owlready2.
    Returns stats dict and list of applied restrictions.
    """
    stats = {
        "llm_proposed": 0,
        "applied":      0,
        "invalid_class": 0,
        "invalid_prop":  0,
        "invalid_target":0,
        "duplicate":     0,
    }
    applied_log = []

    with onto:
        for item in llm_results:
            if not isinstance(item, dict):
                continue
            cls_name   = item.get("class", "")
            prop_local = item.get("property", "")
            tgt_name   = item.get("target", "")
            rationale  = item.get("rationale", "")
            stats["llm_proposed"] += 1

            # validate class
            cls = new_classes.get(cls_name)
            if cls is None:
                stats["invalid_class"] += 1
                continue

            # validate property
            prop_uri = ALLOWED_PROPERTIES.get(prop_local)
            if prop_uri is None:
                stats["invalid_prop"] += 1
                continue
            prop = IRIS[prop_uri]
            if prop is None:
                stats["invalid_prop"] += 1
                continue

            # validate target
            if tgt_name not in valid_targets:
                stats["invalid_target"] += 1
                continue
            tgt = new_classes.get(tgt_name) or all_dpv.get(tgt_name)
            if tgt is None:
                # try IRIS resolution across all loaded namespaces
                for ns in (DPV_NS, DPV_GDPR_NS, DPV_RISK_NS,
                           DPV_PD_NS, DPV_AI_NS, DPV_AIACT_NS, FALLRISK_NS):
                    tgt = IRIS[ns + tgt_name]
                    if tgt is not None:
                        break
            if tgt is None:
                stats["invalid_target"] += 1
                continue

            # check duplicate
            existing = existing_restrictions.get(cls_name, set())
            pair = (prop_uri, tgt.iri if hasattr(tgt, "iri") else str(tgt))
            if pair in existing:
                stats["duplicate"] += 1
                continue

            # apply
            cls.is_a.append(prop.some(tgt))
            if cls_name not in existing_restrictions:
                existing_restrictions[cls_name] = set()
            existing_restrictions[cls_name].add(pair)
            stats["applied"] += 1
            applied_log.append({
                "class":     cls_name,
                "property":  prop_local,
                "target":    tgt_name,
                "rationale": rationale,
            })

    return stats, applied_log


# serialization (same filter logic as phase1_fix.py)

def serialize_clean(onto):
    print("Serializing to v4 …")
    tmp = OUT_V4 + ".nt"
    onto.save(file=tmp, format="ntriples")

    g_raw = Graph()
    g_raw.parse(tmp, format="nt")
    os.remove(tmp)

    kep_subjects = {
        s for s, p, o in g_raw
        if isinstance(s, URIRef) and str(s).startswith(FALLRISK_NS)
    }
    kep_bnodes: set = set()
    frontier = {
        o for s, p, o in g_raw
        if s in kep_subjects and isinstance(o, BNode)
    }
    while frontier:
        kep_bnodes |= frontier
        frontier = {
            o for bn in frontier
            for s, p, o in g_raw.triples((bn, None, None))
            if isinstance(o, BNode) and o not in kep_bnodes
        }

    allowed = kep_subjects | kep_bnodes
    g_clean = Graph()
    for s, p, o in g_raw:
        if s in allowed:
            g_clean.add((s, p, o))

    # keep property declarations from v3
    g_v3 = Graph()
    g_v3.parse(IN_V3)
    for subj in g_v3.subjects(RDF.type, OWL.ObjectProperty):
        for s, p, o in g_v3.triples((subj, None, None)):
            g_clean.add((s, p, o))

    # ontology declaration
    onto_uri = URIRef(FALLRISK_NS.rstrip("#"))
    g_clean.add((onto_uri, RDF.type, OWL.Ontology))

    g_clean.bind("fallrisk", Namespace(FALLRISK_NS))
    g_clean.bind("dpv",      Namespace(DPV_NS))
    g_clean.bind("dpv-risk", Namespace(DPV_RISK_NS))
    g_clean.bind("dpv-pd",   Namespace(DPV_PD_NS))
    g_clean.bind("dpv-ai",   Namespace(DPV_AI_NS))
    g_clean.bind("gdpr",     Namespace(DPV_GDPR_NS))
    g_clean.bind("aiact",    Namespace(DPV_AIACT_NS))

    g_clean.serialize(destination=OUT_V4, format="xml")
    n = len(g_clean)
    print(f"  {n} triples  ->  {OUT_V4}\n")
    return n



# main

def main():
    if not GROQ_API_KEY:
        sys.exit("GROQ_API_KEY not set")
    for f in (IN_V3, CLASSES_JSON, CHUNKS_JSON):
        if not os.path.exists(f):
            sys.exit(f"Input not found: {f}")
    os.makedirs(OUT_DIR, exist_ok=True)

    t_start = time.time()

    # load
    all_dpv = load_dpv()
    onto, new_classes, existing_restrictions = load_v3(all_dpv)

    # load chunks (index by chunk_id)
    with open(CHUNKS_JSON, encoding="utf-8") as f:
        chunks_raw = json.load(f)
    chunks_by_id = {c["chunk_id"]: c for c in chunks_raw}

    # find unrestricted classes
    chunk_to_classes = find_unrestricted(new_classes, existing_restrictions, CLASSES_JSON)

    # build allowed targets
    valid_targets      = build_allowed_targets(new_classes, all_dpv)
    allowed_targets_sample = build_target_sample(new_classes)

    # LLM extraction loop
    client      = Groq(api_key=GROQ_API_KEY)
    all_llm_raw = []
    all_results = []

    total_chunks  = len(chunk_to_classes)
    done_chunks   = 0

    print(f"Starting LLM restriction pass  ({total_chunks} chunks) …\n")

    for chunk_id, class_names in chunk_to_classes.items():
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            print(f"  [skip] chunk not found: {chunk_id}")
            continue

        done_chunks += 1
        print(f"  [{done_chunks}/{total_chunks}] {chunk_id}  "
              f"({len(class_names)} classes)")

        results = extract_restrictions_for_chunk(
            client, chunk, class_names, allowed_targets_sample, all_llm_raw)

        if results:
            all_results.extend(results)
            proposed = len(results)
            print(f"    LLM proposed {proposed} restriction(s)")
        else:
            print(f"    LLM proposed 0 restrictions")

        # checkpoint raw log
        with open(OUT_RAW, "w", encoding="utf-8") as f:
            json.dump(all_llm_raw, f, indent=2, ensure_ascii=False)

    print(f"\nLLM pass complete - {len(all_results)} total proposed\n")

    # validate + apply
    print("Validating and applying restrictions …")
    stats, applied_log = validate_and_apply(
        all_results, onto, new_classes, all_dpv,
        existing_restrictions, valid_targets)

    print(f"  proposed:       {stats['llm_proposed']}")
    print(f"  applied:        {stats['applied']}")
    print(f"  invalid class:  {stats['invalid_class']}")
    print(f"  invalid prop:   {stats['invalid_prop']}")
    print(f"  invalid target: {stats['invalid_target']}")
    print(f"  duplicates:     {stats['duplicate']}\n")

    # reasoner
    print("Running HermiT …")
    t_r = time.time()
    try:
        sync_reasoner_hermit(infer_property_values=False)
        unsat = list(default_world.inconsistent_classes())
        reas_status = "PASS" if not unsat else f"FAIL ({len(unsat)})"
        print(f"  {reas_status}  ({time.time()-t_r:.1f}s)\n")
        if unsat:
            for u in unsat:
                print(f"  UNSAT: {u}")
            sys.exit("Reasoner failed - check LLM-applied restrictions.")
    except Exception as e:
        print(f"  [error] {e}\n")
        sys.exit(1)

    # serialize
    n_triples = serialize_clean(onto)

    # count final restrictions
    g_check = Graph()
    g_check.parse(OUT_V4)
    n_final_rest = sum(1 for _ in g_check.triples((None, OWL.someValuesFrom, None)))
    n_classes    = sum(1 for _ in g_check.subjects(RDF.type, OWL.Class)
                       if str(_).startswith(FALLRISK_NS))

    elapsed = time.time() - t_start

    # write log
    applied_lines = "\n".join(
        f"  - {r['class']} -> {r['property']} some {r['target']}\n"
        f"    Rationale: {r['rationale']}"
        for r in applied_log
    )
    with open(OUT_LOG, "w", encoding="utf-8") as f:
        f.write(f"""# Phase 1 LLM Restrictions Log  (v3 -> v4)

## Stats
- Chunks processed      : {done_chunks}
- Classes without restr : {sum(len(v) for v in chunk_to_classes.values())}
- LLM proposed          : {stats['llm_proposed']}
- Applied               : {stats['applied']}
- Rejected (class)      : {stats['invalid_class']}
- Rejected (property)   : {stats['invalid_prop']}
- Rejected (target)     : {stats['invalid_target']}
- Duplicates skipped    : {stats['duplicate']}
- Total restrictions v4 : {n_final_rest}
- Total classes v4      : {n_classes}
- Total triples v4      : {n_triples}
- Reasoner              : PASS
- Time                  : {elapsed:.1f}s

## Applied restrictions
{applied_lines if applied_lines else "  (none)"}

## Raw LLM responses
Saved to: {OUT_RAW}
""")

    print("=" * 60)
    print(f"Chunks processed     : {done_chunks}")
    print(f"LLM proposed         : {stats['llm_proposed']}")
    print(f"Applied              : {stats['applied']}")
    print(f"Total restrictions   : {n_final_rest}")
    print(f"Total triples        : {n_triples}")
    print(f"Reasoner             : PASS")
    print(f"Output               : {OUT_V4}")
    print(f"Time                 : {elapsed:.1f}s")
    print("=" * 60)
    print("\nPhase 1 complete. Use dpv-fallrisk-ext-v4.rdf for Phase 2.")


if __name__ == "__main__":
    main()