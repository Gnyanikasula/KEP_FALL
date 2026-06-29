"""
phase1_fix.py  -  v2 -> v3  (deterministic, no LLM)
=====================================================
Run this first. It produces dpv-fallrisk-ext-v3.rdf.
Then run phase1_llm_restrictions.py to produce v4.

What this does:
  1. Loads DPV modules via owlready2 (needed for parent + property resolution)
  2. Reads v2 RDF (rdflib) - correct 621-class hierarchy + labels/comments
  3. Reads v1 RDF (rdflib) - extracts 62 existing someValuesFrom restrictions
  4. Rebuilds ontology in owlready2 (two-pass: create all, then set parents)
  5. Ports v1 restrictions - matched by local class name, skips removed classes
  6. Adds 6 FallRisk domain-specific classes with their restrictions
     (these never appear in regulatory text - added from project description)
  7. Runs HermiT reasoner - exits on any unsatisfiable class
  8. Serializes via owlready2 ntriples -> rdflib filter -> clean RDF/XML (v3)
     Filter: KEP namespace + blank nodes only - no DPV individual leakage
  9. Declares 13 DPV object properties with domain + range in the v3 graph


"""

import os
import sys
import types
import time

import rdflib
from rdflib import Graph, RDF, OWL, RDFS, Namespace, URIRef, BNode, Literal
from owlready2 import (
    get_ontology, default_world, Thing,
    sync_reasoner_hermit, IRIS, ObjectProperty,
)
from dotenv import load_dotenv

load_dotenv()



BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DPV_BASE   = os.environ.get("DPV_BASE", r"D:\dpv-2.2.1")
OUT_DIR    = os.path.join(BASE_DIR, "OUT_CANDIDATES")

IN_V1      = os.path.join(OUT_DIR, "dpv-fallrisk-ext.rdf")
IN_V2      = os.path.join(OUT_DIR, "dpv-fallrisk-ext-v2.rdf")
OUT_V3     = os.path.join(OUT_DIR, "dpv-fallrisk-ext-v3.rdf")
OUT_LOG    = os.path.join(OUT_DIR, "fix_log.md")

FALLRISK_NS = "https://w3id.org/kep/fallrisk#"
DPV_NS      = "https://w3id.org/dpv/owl#"
DPV_RISK_NS = "https://w3id.org/dpv/risk/owl#"
DPV_GDPR_NS = "https://w3id.org/dpv/legal/eu/gdpr/owl#"
DPV_PD_NS   = "https://w3id.org/dpv/pd/owl#"
DPV_AI_NS   = "https://w3id.org/dpv/ai/owl#"
DPV_AIACT_NS= "https://w3id.org/dpv/legal/eu/aiact/owl#"

DPV_MODULES = [
    os.path.join(DPV_BASE, "dpv",   "dpv-owl.rdf"),
    os.path.join(DPV_BASE, "pd",    "pd-owl.rdf"),
    os.path.join(DPV_BASE, "risk",  "risk-owl.rdf"),
    os.path.join(DPV_BASE, "ai",    "ai-owl.rdf"),
    os.path.join(DPV_BASE, "legal", "eu", "gdpr",   "eu-gdpr-owl.rdf"),
    os.path.join(DPV_BASE, "legal", "eu", "aiact",  "eu-aiact-owl.rdf"),
]

# ── 13 DPV object properties to declare with domain + range ──────────────────
# All URIs verified from v1 RDF and DPV v2.2.1 module structure.
# domain/range are URIRef strings — resolved at serialisation time.
# Properties marked (*) — verified present in v1 restrictions.
OBJECT_PROPERTIES = [
    # (*) confirmed in v1 restrictions
    {
        "iri":     DPV_NS + "hasPersonalData",
        "domain":  DPV_NS + "Processing",
        "range":   DPV_NS + "PersonalData",
        "comment": "Personal data involved in the processing activity.",
    },
    {
        "iri":     DPV_NS + "hasOrganisationalMeasure",
        "domain":  DPV_NS + "Processing",
        "range":   DPV_NS + "OrganisationalMeasure",
        "comment": "Organisational measure applied to the processing activity.",
    },
    {
        "iri":     DPV_NS + "hasTechnicalOrganisationalMeasure",
        "domain":  DPV_NS + "Processing",
        "range":   DPV_NS + "TechnicalOrganisationalMeasure",
        "comment": "Technical or organisational measure applied to processing.",
    },
    {
        "iri":     DPV_RISK_NS + "hasRiskAssessment",
        "domain":  DPV_NS + "Processing",
        "range":   DPV_RISK_NS + "RiskAssessment",
        "comment": "Risk assessment associated with the processing activity.",
    },
    # new - high value for compliance KG
    {
        "iri":     DPV_NS + "hasLegalBasis",
        "domain":  DPV_NS + "Processing",
        "range":   DPV_NS + "LegalBasis",
        "comment": "Legal basis under which personal data is processed.",
    },
    {
        "iri":     DPV_NS + "hasPurpose",
        "domain":  DPV_NS + "Processing",
        "range":   DPV_NS + "Purpose",
        "comment": "Purpose for which personal data is processed.",
    },
    {
        "iri":     DPV_NS + "hasDataSubject",
        "domain":  DPV_NS + "Processing",
        "range":   DPV_NS + "DataSubject",
        "comment": "Data subject whose personal data is processed.",
    },
    {
        "iri":     DPV_NS + "hasRight",
        "domain":  DPV_NS + "DataSubject",
        "range":   DPV_NS + "Right",
        "comment": "Right available to the data subject.",
    },
    {
        "iri":     DPV_NS + "hasObligation",
        "domain":  DPV_NS + "Entity",
        "range":   DPV_NS + "Obligation",
        "comment": "Obligation imposed on an entity by regulation.",
    },
    {
        "iri":     DPV_NS + "hasTechnicalMeasure",
        "domain":  DPV_NS + "Processing",
        "range":   DPV_NS + "TechnicalMeasure",
        "comment": "Technical measure applied to processing (MDR / AI Act).",
    },
    {
        "iri":     DPV_NS + "hasNotice",
        "domain":  DPV_NS + "Processing",
        "range":   DPV_NS + "Notice",
        "comment": "Notice provided to data subjects (transparency obligations).",
    },
    
    {
        "iri":  DPV_NS + "hasRisk",
        "domain":  DPV_NS + "Processing",
        "range": DPV_NS + "Risk",
        "comment": "Risk associated with the processing activity.",},
    
    # {
    #     "iri":     DPV_NS + "hasSafeguard",
    #     "domain":  DPV_NS + "Processing",
    #     "range":   DPV_NS + "Safeguard",
    #     "comment": "Safeguard applied to the processing activity.",
    # },
    {
    "iri":     DPV_NS + "isMitigatedByMeasure",
    "domain":  DPV_NS + "Risk",
    "range":   DPV_NS + "TechnicalOrganisationalMeasure",
    "comment": "Indicates a risk is mitigated by a technical or organisational measure.",
    },
]

# FallRisk domain-specific classes
# These concepts are NOT in any regulatory text.
DOMAIN_CLASSES = [
    {
        "name":   "FallRiskPrediction",
        "parent": "AutomatedDecisionMaking",      # dpv:AutomatedDecisionMaking
        "label":  "An automated prediction of fall risk for a patient generated "
                  "by the SHIELD v2 AI system from wearable sensor data.",
        "source": "KEP Variant 5 — Fall-Risk Prediction from Wearables "
                  "(Skein Ltd × OPORA Health)",
        "restrictions": [
            (DPV_NS      + "hasPersonalData",           DPV_GDPR_NS + "HealthData"),
            (DPV_NS      + "hasOrganisationalMeasure",  DPV_NS      + "HumanInvolvementForOversight"),
        ],
    },
    {
        "name":   "FallRiskScore",
        "parent": "InferredPersonalData",           # dpv-pd or dpv core
        "label":  "Numerical fall-risk probability score derived from gait and "
                  "accelerometer data by the SHIELD v2 model.",
        "source": "KEP Variant 5 — Fall-Risk Prediction from Wearables",
        "restrictions": [
            (DPV_NS + "hasPersonalData", DPV_GDPR_NS + "HealthData"),
        ],
    },
    {
        "name":   "AccelerometerReading",
        "parent": "PersonalData",                   # dpv:PersonalData
        "label":  "Raw 3-axis accelerometer measurements captured by a wearable "
                  "sensor worn by the patient.",
        "source": "KEP Variant 5 — Fall-Risk Prediction from Wearables",
        "restrictions": [],
    },
    {
        "name":   "GaitAnalysisOutput",
        "parent": "InferredPersonalData",
        "label":  "Derived gait parameters (stride length, cadence, asymmetry "
                  "index) computed from accelerometer and gyroscope sensor data.",
        "source": "KEP Variant 5 — Fall-Risk Prediction from Wearables",
        "restrictions": [
            (DPV_NS + "hasPersonalData", DPV_GDPR_NS + "HealthData"),
        ],
    },
    {
        "name":   "WearableSensor",
        "parent": "Device",                         # dpv:Device
        "label":  "Wearable IMU (accelerometer/gyroscope) device worn by a "
                  "patient to capture movement data for fall-risk assessment.",
        "source": "KEP Variant 5 — Fall-Risk Prediction from Wearables",
        "restrictions": [],
    },
    {
        "name":   "WearableDataProcessing",
        "parent": "Processing",                     # dpv:Processing
        "label":  "Processing of personal data captured by wearable sensors "
                  "for fall-risk prediction and clinical decision support.",
        "source": "KEP Variant 5 — Fall-Risk Prediction from Wearables",
        "restrictions": [
            (DPV_NS + "hasPersonalData",          DPV_GDPR_NS + "HealthData"),
            (DPV_NS + "hasOrganisationalMeasure", DPV_NS      + "HumanInvolvementForOversight"),
        ],
    },
]



# helpers
def local(uri: str) -> str:
    """Return local name from a URI."""
    return uri.split("#")[-1] if "#" in uri else uri.split("/")[-1]


def load_dpv():
    print("Loading DPV modules …")
    t0 = time.time()
    for p in DPV_MODULES:
        if not os.path.exists(p):
            sys.exit(f"  DPV module not found: {p}")
        get_ontology(p).load()
    total = len(list(default_world.classes()))
    print(f"  {total} DPV classes loaded  ({time.time()-t0:.1f}s)\n")
    return {c.name: c for c in default_world.classes()}


def read_v2_structure():
    """
    Read v2 RDF via rdflib.
    Returns:
        kep_classes: dict  local_name -> {parent_uri, label, comment}
    """
    print("Reading v2 structure …")
    g = Graph()
    g.parse(IN_V2)
    kep_classes = {}
    for subj in g.subjects(RDF.type, OWL.Class):
        if not str(subj).startswith(FALLRISK_NS):
            continue
        name = local(str(subj))
        parents = [o for o in g.objects(subj, RDFS.subClassOf)
                   if not isinstance(o, BNode)]
        parent_uri = str(parents[0]) if parents else None
        labels   = list(g.objects(subj, RDFS.label))
        comments = list(g.objects(subj, RDFS.comment))
        kep_classes[name] = {
            "parent_uri": parent_uri,
            "label":      str(labels[0])   if labels   else name,
            "comment":    str(comments[0]) if comments else "",
        }
    print(f"  {len(kep_classes)} KEP classes in v2\n")
    return kep_classes


def read_v1_restrictions():
    """
    Read v1 RDF via rdflib - extract all someValuesFrom restrictions.
    Returns list of {class_local, prop_uri, target_uri}
    """
    print("Reading v1 restrictions …")
    g = Graph()
    g.parse(IN_V1)
    restrictions = []
    for bnode in g.subjects(RDF.type, OWL.Restriction):
        props   = list(g.objects(bnode, OWL.onProperty))
        targets = list(g.objects(bnode, OWL.someValuesFrom))
        parents = list(g.subjects(RDFS.subClassOf, bnode))
        if not (props and targets and parents):
            continue
        cls_uri = str(parents[0])
        if not cls_uri.startswith(FALLRISK_NS):
            continue
        restrictions.append({
            "class_local": local(cls_uri),
            "prop_uri":    str(props[0]),
            "target_uri":  str(targets[0]),
        })
    print(f"  {len(restrictions)} restrictions found in v1\n")
    return restrictions


def build_ontology(kep_classes, all_dpv):
    """
    Rebuild ontology in owlready2.
    Pass 1: create all KEP classes with Thing as placeholder parent.
    Pass 2: set correct parent (DPV class or other KEP class).
    Returns (onto, new_classes_dict)
    """
    print("Building ontology (two-pass) …")
    onto = get_ontology(FALLRISK_NS)
    new_classes = {}

    # pass 1 — create all classes
    with onto:
        for name, info in kep_classes.items():
            cls = types.new_class(name, (Thing,))
            cls.label   = [info["label"]]
            cls.comment = [info["comment"]]
            new_classes[name] = cls

    # pass 2 — set parents
    fixed = 0
    for name, info in kep_classes.items():
        p_uri = info["parent_uri"]
        if not p_uri or p_uri.endswith("#Thing"):
            continue
        p_local = local(p_uri)
        # try DPV first
        parent_cls = all_dpv.get(p_local)
        # then try local KEP class
        if parent_cls is None:
            parent_cls = new_classes.get(p_local)
        if parent_cls is None:
            # resolve via owlready2 IRIS directly from URI
            parent_cls = IRIS[p_uri]
        if parent_cls is None:
            continue
        new_classes[name].is_a = [parent_cls]
        fixed += 1

    print(f"  created {len(new_classes)} classes  |  {fixed} parented\n")
    return onto, new_classes


def port_restrictions(v1_restrictions, onto, new_classes, all_dpv):
    """
    Apply v1 restrictions to the rebuilt ontology.
    Skips classes that were removed in v2 (DPV duplicates).
    """
    print("Porting v1 restrictions …")
    applied = skipped_no_class = skipped_no_prop = skipped_no_target = 0

    with onto:
        for r in v1_restrictions:
            cls = new_classes.get(r["class_local"])
            if cls is None:
                skipped_no_class += 1
                continue
            prop = IRIS[r["prop_uri"]]
            if prop is None:
                skipped_no_prop += 1
                print(f"  [warn] property not found: {r['prop_uri']}")
                continue
            tgt = IRIS[r["target_uri"]]
            if tgt is None:
                # try by local name in DPV
                tgt = all_dpv.get(local(r["target_uri"]))
            if tgt is None:
                skipped_no_target += 1
                print(f"  [warn] target not found: {r['target_uri']}")
                continue
            cls.is_a.append(prop.some(tgt))
            applied += 1

    print(f"  applied {applied}  |  skipped (no class) {skipped_no_class}  "
          f"|  (no prop) {skipped_no_prop}  |  (no target) {skipped_no_target}\n")
    return applied


def add_domain_classes(onto, new_classes, all_dpv):
    """
    Add FallRisk domain-specific classes with their restrictions.
    These are application-layer classes not in any regulatory text.
    """
    print("Adding FallRisk domain classes …")
    added = restricted = 0

    with onto:
        for dc in DOMAIN_CLASSES:
            name = dc["name"]
            if name in new_classes:
                print(f"  [skip] {name} already exists")
                continue

            # resolve parent
            parent_cls = all_dpv.get(dc["parent"]) or new_classes.get(dc["parent"]) or Thing
            cls = types.new_class(name, (parent_cls,))
            cls.label   = [dc["label"]]
            cls.comment = [f"Source: {dc['source']}"]
            new_classes[name] = cls
            added += 1
            print(f"  + {name:<35s} <- {dc['parent']}")

            # apply restrictions
            for prop_uri, target_uri in dc["restrictions"]:
                prop = IRIS[prop_uri]
                tgt  = IRIS[target_uri]
                if prop is None:
                    prop = all_dpv.get(local(prop_uri))
                if tgt is None:
                    tgt = all_dpv.get(local(target_uri))
                if prop is None or tgt is None:
                    print(f"    [warn] could not resolve restriction "
                          f"{local(prop_uri)} some {local(target_uri)}")
                    continue
                cls.is_a.append(prop.some(tgt))
                restricted += 1
                print(f"    -> {local(prop_uri)} some {local(target_uri)}")

    print(f"\n  added {added} domain classes  |  {restricted} restrictions applied\n")
    return added


def run_reasoner():
    print("Running HermiT …")
    t0 = time.time()
    try:
        sync_reasoner_hermit(infer_property_values=False)
        unsat = list(default_world.inconsistent_classes())
        status = "PASS" if not unsat else f"FAIL ({len(unsat)} unsatisfiable)"
        print(f"  {status}  ({time.time()-t0:.1f}s)\n")
        if unsat:
            for u in unsat:
                print(f"  UNSAT: {u}")
            sys.exit("Reasoner failed — fix ontology before proceeding.")
        return True
    except Exception as e:
        print(f"  [error] {e}\n  Check: java -version  (Java 11+ required)\n")
        sys.exit(1)


def serialize_clean(onto):
    """
    Serialize owlready2 ontology to a clean RDF/XML file.

    Problem in v2: owlready2 leaked DPV individuals into the output.
    Fix: save as ntriples -> parse with rdflib -> keep only:
      - triples whose subject is in the KEP namespace
      - blank nodes transitively referenced by KEP subjects (restriction nodes)
    Then append property declarations (added via rdflib directly).
    """
    print("Serializing to v3 …")
    tmp = OUT_V3 + ".nt"
    onto.save(file=tmp, format="ntriples")

    g_raw = Graph()
    g_raw.parse(tmp, format="nt")
    os.remove(tmp)

    # collect KEP-namespace subjects
    kep_subjects = {
        s for s, p, o in g_raw
        if isinstance(s, URIRef) and str(s).startswith(FALLRISK_NS)
    }

    # collect blank nodes transitively referenced by KEP subjects
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

    # build filtered graph
    g_clean = Graph()
    for s, p, o in g_raw:
        if s in allowed:
            g_clean.add((s, p, o))

    # add owl:Ontology declaration
    onto_uri = URIRef(FALLRISK_NS.rstrip("#"))
    g_clean.add((onto_uri, RDF.type, OWL.Ontology))

    # declare 13 DPV object properties with domain + range
    # Added here (not in owlready2) to avoid property redefinition conflicts.
    verified = 0
    skipped  = 0
    for prop_def in OBJECT_PROPERTIES:
        p_uri = URIRef(prop_def["iri"])
        d_uri = URIRef(prop_def["domain"])
        r_uri = URIRef(prop_def["range"])
        # sanity-check: property must be resolvable in loaded DPV
        if IRIS[prop_def["iri"]] is None:
            print(f"  [warn] property not in DPV, skipping: {local(prop_def['iri'])}")
            skipped += 1
            continue
        g_clean.add((p_uri, RDF.type,       OWL.ObjectProperty))
        g_clean.add((p_uri, RDFS.domain,    d_uri))
        g_clean.add((p_uri, RDFS.range,     r_uri))
        g_clean.add((p_uri, RDFS.comment,   Literal(prop_def["comment"])))
        verified += 1

    print(f"  {verified} properties declared  |  {skipped} skipped (not in DPV)")

    # bind prefixes
    g_clean.bind("fallrisk", Namespace(FALLRISK_NS))
    g_clean.bind("dpv",      Namespace(DPV_NS))
    g_clean.bind("dpv-risk", Namespace(DPV_RISK_NS))
    g_clean.bind("dpv-pd",   Namespace(DPV_PD_NS))
    g_clean.bind("dpv-ai",   Namespace(DPV_AI_NS))
    g_clean.bind("gdpr",     Namespace(DPV_GDPR_NS))
    g_clean.bind("aiact",    Namespace(DPV_AIACT_NS))

    g_clean.serialize(destination=OUT_V3, format="xml")
    print(f"  {len(g_clean)} triples  ->  {OUT_V3}\n")
    return len(g_clean), verified



# main

def main():
    t_start = time.time()

    for f in (IN_V1, IN_V2):
        if not os.path.exists(f):
            sys.exit(f"Input not found: {f}")
    os.makedirs(OUT_DIR, exist_ok=True)

    all_dpv         = load_dpv()
    kep_classes     = read_v2_structure()
    v1_restrictions = read_v1_restrictions()
    onto, new_classes = build_ontology(kep_classes, all_dpv)
    ported          = port_restrictions(v1_restrictions, onto, new_classes, all_dpv)
    domain_added    = add_domain_classes(onto, new_classes, all_dpv)
    run_reasoner()
    n_triples, n_props = serialize_clean(onto)

    elapsed = time.time() - t_start

    # count restrictions in output for log
    g_check = Graph()
    g_check.parse(OUT_V3)
    n_restrictions = sum(1 for _ in g_check.triples((None, OWL.someValuesFrom, None)))
    n_classes = sum(1 for _ in g_check.subjects(RDF.type, OWL.Class)
                    if str(_).startswith(FALLRISK_NS))
    n_obj_props = sum(1 for _ in g_check.subjects(RDF.type, OWL.ObjectProperty))

    with open(OUT_LOG, "w", encoding="utf-8") as f:
        f.write(f"""# Phase 1 Fix Log  (v2 -> v3)

- Input v1 (restrictions source) : {IN_V1}
- Input v2 (hierarchy source)    : {IN_V2}
- Output v3                      : {OUT_V3}

## Counts
- KEP classes          : {n_classes}  ({len(kep_classes)} from v2  +  {domain_added} domain classes)
- OWL restrictions     : {n_restrictions}  ({ported} ported from v1,  domain class restrictions extra)
- Object properties    : {n_obj_props}  (declared with domain + range)
- Total triples        : {n_triples}
- Reasoner             : PASS

## Domain classes added
{chr(10).join('- ' + dc['name'] for dc in DOMAIN_CLASSES)}

## Object properties declared
{chr(10).join('- ' + local(p['iri']) for p in OBJECT_PROPERTIES)}

## Time
- {elapsed:.1f}s

## Next step
Run phase1_llm_restrictions.py  ->  v3 + LLM restriction pass  ->  v4
""")

    print("=" * 60)
    print(f"KEP classes       : {n_classes}")
    print(f"OWL restrictions  : {n_restrictions}")
    print(f"Object properties : {n_obj_props}")
    print(f"Total triples     : {n_triples}")
    print(f"Reasoner          : PASS")
    print(f"Output            : {OUT_V3}")
    print(f"Time              : {elapsed:.1f}s")
    print("=" * 60)
    print("\nNext: run phase1_llm_restrictions.py")


if __name__ == "__main__":
    main()