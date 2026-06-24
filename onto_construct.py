import os
import sys
import re
import json
import time
import types
from dotenv import load_dotenv
from groq import Groq
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from owlready2 import get_ontology, default_world, Thing, sync_reasoner_hermit, IRIS, ObjectProperty
import rdflib
from pathlib import Path
load_dotenv()

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DPV_BASE     = os.environ.get("DPV_BASE", r"D:\dpv-2.2.1")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")




CHUNKS_JSON    = os.path.join(BASE_DIR, "regulatory_chunks.json")
OUT_DIR        = os.path.join(BASE_DIR, "OUT_CANDIDATES")
OUT_CANDIDATES = os.path.join(OUT_DIR, "candidate_concepts.json")
OUT_ALIGNMENT  = os.path.join(OUT_DIR, "alignment_results.json")
OUT_ONTOLOGY   = os.path.join(OUT_DIR, "dpv-fallrisk-ext.rdf")
OUT_CLASSES    = os.path.join(OUT_DIR, "classes_created.json")
OUT_DEDUP      = os.path.join(OUT_DIR, "dedup_report.json")
OUT_LOG        = os.path.join(OUT_DIR, "build_log.md")

MODEL           = "meta-llama/llama-4-scout-17b-16e-instruct"
MAX_TOKENS      = 1200
REQUEST_DELAY   = 2.2
MAX_RETRIES     = 5
RETRY_BASE      = 15.0
ALIGN_THRESHOLD = 0.85
DEDUP_THRESHOLD = 0.82
FALLRISK_NS     = "https://w3id.org/kep/fallrisk#"

# DPV_MODULES = [
#     os.path.join(DPV_BASE, "dpv/dpv-owl.ttl"),
#     os.path.join(DPV_BASE, "pd/pd-owl.ttl"),
#     os.path.join(DPV_BASE, "risk/risk-owl.ttl"),
#     os.path.join(DPV_BASE, "ai/ai-owl.ttl"),
#     os.path.join(DPV_BASE, "legal/eu/gdpr/gdpr-owl.ttl"),
#     os.path.join(DPV_BASE, "legal/eu/aiact/eu-aiact-owl.ttl"),
# ]

DPV_MODULES = [
    os.path.join(DPV_BASE, "dpv", "dpv-owl.rdf"),
    os.path.join(DPV_BASE, "pd", "pd-owl.rdf"),
    os.path.join(DPV_BASE, "risk", "risk-owl.rdf"),
    os.path.join(DPV_BASE, "ai", "ai-owl.rdf"),
    os.path.join(DPV_BASE, "legal", "eu", "gdpr", "eu-gdpr-owl.rdf"),
    os.path.join(DPV_BASE, "legal", "eu", "aiact", "eu-aiact-owl.rdf"),
]

# rule-based restrictions added automatically based on chunk source and class semantics
# every property and target was verified to exist in DPV v2.2.1
RESTRICTION_RULES = [
    {
        "chunk_prefix":  "GDPR_Art9",
        "parent_in":     {"Purpose", "Processing", "MedicalHealth", "SpecialCategoryPersonalData"},
        "restrictions":  [("hasPersonalData", "SpecialCategoryPersonalData")],
    },
    {
        "chunk_prefix":  "GDPR_Art9",
        "name_contains": ["Health", "Medical", "Patient", "Clinical", "Preventive", "Occupational"],
        "restrictions":  [("hasPersonalData", "HealthData")],
    },
    {
        "chunk_prefix":  "GDPR_Art22",
        "restrictions":  [("hasOrganisationalMeasure", "HumanInvolvementForOversight")],
    },
    {
        "chunk_prefix":  "GDPR_Art32",
        "restrictions":  [("hasTechnicalOrganisationalMeasure", "DataSecurityManagement")],
    },
    {
        "chunk_prefix":  "GDPR_Art35",
        "restrictions":  [("hasRiskAssessment", "RiskAssessment")],
    },
    {
        "chunk_prefix":  None,
        "name_contains": ["PrivacyByDesign", "DataProtectionByDesign", "DataMinimisation"],
        "restrictions":  [("hasTechnicalOrganisationalMeasure", "PrivacyByDesign")],
    },
    {
        "chunk_prefix":  None,
        "name_contains": ["PrivacyByDefault", "DataProtectionByDefault"],
        "restrictions":  [("hasTechnicalOrganisationalMeasure", "PrivacyByDefault")],
    },
    {
        "chunk_prefix":  None,
        "name_contains": ["HumanOversight", "HumanControl", "HumanIntervention"],
        "restrictions":  [("hasOrganisationalMeasure", "HumanInvolvementForOversight")],
    },
    {
        "chunk_prefix":  None,
        "name_contains": ["RiskManagement", "RiskMitigation"],
        "restrictions":  [("hasRiskAssessment", "RiskAssessment")],
    },
    {
        "chunk_prefix":  None,
        "name_contains": ["FallRisk"],
        "restrictions":  [("hasPersonalData", "HealthData"), ("hasLegalBasis", "A9-2-h")],
    },
    {
        "chunk_prefix":  None,
        "name_contains": ["AutomatedDecision", "AutomatedIndividual"],
        "restrictions":  [("hasOrganisationalMeasure", "HumanInvolvementForOversight")],
    },
]

STEP1_SYSTEM = """\
You are a regulatory ontology engineer extending the W3C Data Privacy Vocabulary (DPV)
for a fall-risk prediction AI system using wearable sensors (Skein Ltd x OPORA Health).

For the regulatory text chunk provided, identify concepts that are:
- explicitly named or clearly implied by the text
- NOT already in DPV (add only regulation-specific or domain-specific gaps)
- useful as OWL classes in a compliance knowledge graph

Return ONLY a valid JSON array.

Schema:

[
  {
    "candidate_name": "ExampleConcept",
    "definition": "Definition text.",
    "suggested_dpv_parent": "Purpose",
    "suggested_restrictions": [],
    "source_regulation": "GDPR",
    "source_article_reference": "GDPR, Article 5(1)(a)"
  }
]

Rules:
- Output MUST be a JSON array.
- Every array element MUST be a JSON object.
- Do NOT use candidate names as keys.
- Do NOT return dictionaries.
- Do NOT return markdown.
- Do NOT return explanations.
- If no concepts exist, return [].
"""

STEP1_REPAIR_SYSTEM = """
Convert the provided text into a VALID JSON array.

Required schema:

[
  {
    "candidate_name": "ExampleConcept",
    "definition": "Definition text",
    "suggested_dpv_parent": null,
    "suggested_restrictions": [],
    "source_regulation": "GDPR",
    "source_article_reference": "GDPR, Article X"
  }
]

Output ONLY JSON.
No markdown.
No explanations.
"""

STEP2_SYSTEM = """\
Decide whether a candidate OWL concept duplicates an existing DPV term.
Return ONLY:
{"decision": "genuinely_new"|"reuse_existing", "matched_term": null|"<name>",
 "confidence": 0.0-1.0, "reason": "<one sentence>"}"""
 
STEP2_REPAIR_SYSTEM = """
Convert the provided text into a VALID JSON object.

Required schema:

{
  "decision": "genuinely_new" | "reuse_existing",
  "matched_term": null | "<name>",
  "confidence": 0.0,
  "reason": "<one sentence>"
}

Output ONLY JSON.
No markdown.
No explanations.
"""


def load_dpv():
    print("Loading DPV...")
    t0 = time.time()
    for p in DPV_MODULES:
        if not os.path.exists(p):
            sys.exit(f"DPV module not found: {p}")
        # onto = get_ontology(Path(p).resolve().as_uri()).load()
        # onto = get_ontology(p).load()
        onto = get_ontology(p).load()
        # onto = get_ontology(p).load(format="turtle")
        print(f"  {onto.base_iri:50s} {len(list(onto.classes()))}")
    total = len(list(default_world.classes()))
    print(f"  total: {total} classes  ({time.time()-t0:.1f}s)\n")
    index = []
    for cls in default_world.classes():
        iri   = cls.iri
        local = iri.split("#")[-1] if "#" in iri else iri.split("/")[-1]
        label = ""
        try:
            lb = cls.label; label = lb[0] if lb else ""
        except Exception:
            pass
        index.append({"iri": iri, "local_name": local, "label": str(label)})
    return index


def sanitize(name):
    if not name:
        return ""
    return re.sub(r"[^a-zA-Z0-9_]", "", str(name))


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
            if attempt < MAX_RETRIES and any(k in err for k in ("rate_limit", "429", "too many")):
                m = re.search(r"try again in ([0-9.]+)s", err)
                wait = float(m.group(1)) + 2.0 if m else delay
                print(f"    rate-limit, waiting {wait:.0f}s...")
                time.sleep(wait)
                delay *= 2
            else:
                raise

def call_llm_parse(client, raw, repair_system):
    repair_raw = call_llm(client, [
        {"role": "system", "content": repair_system},
        {"role": "user", "content": raw},
    ])
    return parse_json(repair_raw)

def parse_json(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw.strip())


def resolve_parent(name, class_index, created_so_far):
    if not name:
        return None
    s  = sanitize(name)
    sl = s.lower()
    if s in created_so_far:
        return created_so_far[s]
    for e in class_index:
        if e["local_name"].lower() == sl:
            return IRIS[e["iri"]]
    return None


def dpv_class(name, all_dpv):
    if not name:
        return None
    nl = sanitize(name).lower()
    for k, v in all_dpv.items():
        if k.lower() == nl:
            return v
    return None


def rule_fires(rule, chunk_id, class_name, parent_local):
    if rule.get("chunk_prefix") and not chunk_id.startswith(rule["chunk_prefix"]):
        return False
    if "name_contains" in rule:
        if not any(t in class_name for t in rule["name_contains"]):
            return False
    if "parent_in" in rule:
        if parent_local not in rule["parent_in"]:
            return False
    return True


def add_restriction(cls, prop_name, target_name, all_props, all_dpv, onto):
    prop = all_props.get(prop_name)
    tgt  = dpv_class(target_name, all_dpv)
    if prop is None or tgt is None:
        return False
    with onto:
        cls.is_a.append(prop.some(tgt))
    return True


# step 1: send each chunk to the LLM, extract candidate concepts, checkpoint after each
def step1(chunks, dpv_names, client):
    print("Step 1 — candidate extraction")
    existing = {}
    if os.path.exists(OUT_CANDIDATES):
        with open(OUT_CANDIDATES, encoding="utf-8") as f:
            for item in json.load(f):
                existing[item["chunk_id"]] = item
        print(f"  resuming from {len(existing)} done")

    dpv_sample = ", ".join(dpv_names[:400])
    results = []
    failed  = []

    for chunk in chunks:
        cid = chunk["chunk_id"]
        if cid in existing:
            results.append(existing[cid])
            continue

        user_msg = (
            f"Regulation: {chunk['regulation']}\n"
            f"Breadcrumb: {chunk['context_header']}\n"
            + (f"Point: ({chunk['sub_point']})\n" if chunk.get("sub_point") else "")
            + f"Text:\n{chunk['text']}\n\n"
            f"Existing DPV (do not re-propose): {dpv_sample}"
        )
        candidates = []

        try:
            raw = call_llm(client, [
                {"role": "system", "content": STEP1_SYSTEM},
                {"role": "user", "content": user_msg},
            ])

            try:
                candidates = parse_json(raw)
            except Exception:
                print(f"  [repair] {cid}")
                candidates = call_llm_parse(
                    client,
                    raw,
                    STEP1_REPAIR_SYSTEM
                )

            if not isinstance(candidates, list):
                candidates = []

        except Exception as e:
            print(f"  [fail] {cid}: {e}")
            print("RAW RESPONSE:")
            print(raw[:3000])
            failed.append(cid)
        entry = {
            "chunk_id":          cid,
            "regulation":        chunk["regulation"],
            "context_header":    chunk["context_header"],
            "sub_point":         chunk.get("sub_point", ""),
            "candidates":        candidates,
            "extraction_failed": cid in failed,
        }
        existing[cid] = entry
        results.append(entry)
        with open(OUT_CANDIDATES, "w", encoding="utf-8") as f:
            json.dump(list(existing.values()), f, indent=2, ensure_ascii=False)
        print(f"  {cid}: {len(candidates)} candidates")

    total = sum(len(r["candidates"]) for r in results)
    print(f"  total: {total} candidates, {len(failed)} failed\n")
    return results


# step 2: check each candidate against DPV via TF-IDF + LLM fallback
def step2(step1_results, class_index, client):
    print("Step 2 — DPV alignment")
    existing = {}
    if os.path.exists(OUT_ALIGNMENT):
        with open(OUT_ALIGNMENT, encoding="utf-8") as f:
            for item in json.load(f):
                existing[(item.get("source_chunk_id"), item.get("candidate_name"))] = item
        print(f"  resuming from {len(existing)} done")

    dpv_texts  = [f"{e['local_name']} {e['label']}" for e in class_index]
    vectorizer = TfidfVectorizer(stop_words="english")
    dpv_vecs   = vectorizer.fit_transform(dpv_texts)
    aligned    = []

    for chunk_result in step1_results:
        cid = chunk_result["chunk_id"]
        for cand in chunk_result["candidates"]:
            name = sanitize(cand.get("candidate_name", ""))
            if not name:
                continue
            key = (cid, name)
            if key in existing:
                aligned.append(existing[key])
                continue

            defn       = cand.get("definition", "")
            cand_vec   = vectorizer.transform([f"{name} {defn}"])
            sims       = cosine_similarity(cand_vec, dpv_vecs)[0]
            top_score  = float(sims.max())
            top_match  = class_index[int(sims.argmax())]["local_name"]

            if top_score >= ALIGN_THRESHOLD:
                decision, matched = "reuse_existing", top_match
                reason = f"TF-IDF {top_score:.2f} >= threshold; matches {top_match}"
            else:
                try:
                    raw = call_llm(client, [
                        {"role": "system", "content": STEP2_SYSTEM},
                        {"role": "user", "content":
                        f"Candidate: {name}\nDefinition: {defn}\n"
                        f"Top DPV match: {top_match} (score {top_score:.2f})"},
                    ])

                    try:
                        resp = parse_json(raw)
                    except Exception:
                        print(f"    [repair] {name}")
                        resp = call_llm_parse(
                            client,
                            raw,
                            STEP2_REPAIR_SYSTEM
                        )

                    decision = resp.get("decision", "genuinely_new")
                    matched = resp.get("matched_term")
                    reason = resp.get("reason", "")

                except Exception as e:
                    print(f"    [fail] {name}: {e}")
                    print("RAW RESPONSE:")
                    print(raw[:3000])

                    decision, matched, reason = "_alignment_failed", None, str(e)
                    
            entry = {
                "source_chunk_id":          cid,
                "candidate_name":           name,
                "definition":               defn,
                "suggested_dpv_parent":     sanitize(cand.get("suggested_dpv_parent", "")),
                "suggested_restrictions":   cand.get("suggested_restrictions", []),
                "source_regulation":        cand.get("source_regulation", ""),
                "source_article_reference": cand.get("source_article_reference", ""),
                "alignment": {"decision": decision, "matched_term": matched,
                              "confidence": top_score, "reason": reason},
            }
            existing[key] = entry
            aligned.append(entry)
            with open(OUT_ALIGNMENT, "w", encoding="utf-8") as f:
                json.dump(list(existing.values()), f, indent=2, ensure_ascii=False)

    n_new   = sum(1 for a in aligned if a["alignment"]["decision"] == "genuinely_new")
    n_reuse = sum(1 for a in aligned if a["alignment"]["decision"] == "reuse_existing")
    print(f"  {n_new} genuinely_new, {n_reuse} reuse_existing\n")
    return aligned


# step 3: create OWL classes for novel candidates, apply LLM-suggested + rule-based restrictions
def step3(aligned, class_index, onto, all_props, all_dpv):
    print("Step 3 — create classes and apply restrictions")
    novel         = [c for c in aligned if c["alignment"]["decision"] == "genuinely_new"]
    created       = []
    by_name       = {}
    by_name_lower = {}

    with onto:
        for cand in novel:
            name = cand["candidate_name"]
            if not name or name in by_name:
                continue
            nl = name.lower()
            if nl in by_name_lower:
                canonical = by_name_lower[nl]
                created.append({
                    "name": name, "merged_into": canonical,
                    "parent_requested": cand.get("suggested_dpv_parent"),
                    "parent_resolved": None, "parent_used": None,
                    "source_chunk_id": cand["source_chunk_id"],
                    "restrictions_applied": [],
                })
                continue

            parent_cls   = resolve_parent(cand.get("suggested_dpv_parent"), class_index, by_name)
            parent_ok    = parent_cls is not None
            parent_cls   = parent_cls or Thing
            parent_iri   = parent_cls.iri if hasattr(parent_cls, "iri") else "owl:Thing"
            parent_local = parent_iri.split("#")[-1] if "#" in parent_iri else parent_iri.split("/")[-1]

            new_cls = types.new_class(name, (parent_cls,))
            new_cls.label   = [cand.get("definition", name)]
            new_cls.comment = [
                f"Source: {cand['source_regulation']} — "
                f"{cand['source_article_reference']} "
                f"(chunk {cand['source_chunk_id']})"
            ]
            by_name[name]    = new_cls
            by_name_lower[nl]= name

            chunk_id    = cand["source_chunk_id"]
            restrictions= []

            for r in cand.get("suggested_restrictions", []):
                pl, tl = sanitize(r.get("property", "")), sanitize(r.get("target", ""))
                if pl and tl and add_restriction(new_cls, pl, tl, all_props, all_dpv, onto):
                    restrictions.append({"property": pl, "target": tl, "source": "llm"})

            for rule in RESTRICTION_RULES:
                if rule_fires(rule, chunk_id, name, parent_local):
                    for pl, tl in rule["restrictions"]:
                        already = any(x["property"] == pl and x["target"] == tl for x in restrictions)
                        if not already and add_restriction(new_cls, pl, tl, all_props, all_dpv, onto):
                            restrictions.append({"property": pl, "target": tl, "source": "rule"})

            flag = "" if parent_ok else " [Thing-fallback]"
            print(f"  + {name:<45s} <- {parent_local}{flag}")
            if restrictions:
                print("      " + " | ".join(f"{r['property']} some {r['target']}" for r in restrictions))

            created.append({
                "name":                 name,
                "merged_into":          None,
                "parent_requested":     cand.get("suggested_dpv_parent"),
                "parent_resolved":      parent_ok,
                "parent_used":          parent_iri,
                "source_chunk_id":      chunk_id,
                "restrictions_applied": restrictions,
            })

    merged     = sum(1 for c in created if c.get("merged_into"))
    unresolved = sum(1 for c in created if c["parent_resolved"] is False)
    restricted = sum(1 for c in created if not c.get("merged_into") and c.get("restrictions_applied"))
    print(f"\n  {len(created)-merged} classes, {merged} case-fold dupes, "
          f"{unresolved} Thing-fallbacks, {restricted} with restrictions\n")
    return created


# step 4: run HermiT to confirm no unsatisfiable classes
def step4():
    print("Step 4 — HermiT reasoner")
    try:
        sync_reasoner_hermit(infer_property_values=False)
        unsat = list(default_world.inconsistent_classes())
        print(f"  {'PASS' if not unsat else 'FAIL'} — {len(unsat)} unsatisfiable\n")
        return unsat
    except Exception as e:
        print(f"  [error] {e}  (check java -version)\n")
        return None


# step 5: TF-IDF near-synonym detection between all created classes
def step5(created, aligned):
    print("Step 5 — near-synonym detection")
    live = [c["name"] for c in created if not c.get("merged_into")]
    if len(live) < 2:
        return []
    defs  = {a["candidate_name"]: a.get("definition", "") for a in aligned if a.get("candidate_name")}
    texts = [f"{n} {defs.get(n,'')}" for n in live]
    vec   = TfidfVectorizer(stop_words="english")
    mat   = vec.fit_transform(texts)
    sims  = cosine_similarity(mat)
    flagged = [
        {"class_a": live[i], "class_b": live[j], "similarity": round(float(sims[i, j]), 3)}
        for i in range(len(live))
        for j in range(i + 1, len(live))
        if sims[i, j] >= DEDUP_THRESHOLD
    ]
    flagged.sort(key=lambda x: x["similarity"], reverse=True)
    print(f"  {len(flagged)} pairs flagged\n")
    return flagged


# step 6: serialize the ontology to RDF/XML with namespace prefixes for Protege
def step6(onto):
    print("Step 6 — serialize to RDF/XML")
    tmp = OUT_ONTOLOGY + ".nt"
    onto.save(file=tmp, format="ntriples")
    g = rdflib.Graph()
    g.parse(tmp, format="nt")
    g.bind("fallrisk", rdflib.Namespace(FALLRISK_NS))
    g.bind("dpv",      rdflib.Namespace("https://w3id.org/dpv/owl#"))
    g.bind("dpv-pd",   rdflib.Namespace("https://w3id.org/dpv/pd/owl#"))
    g.bind("dpv-risk", rdflib.Namespace("https://w3id.org/dpv/risk/owl#"))
    g.bind("dpv-ai",   rdflib.Namespace("https://w3id.org/dpv/ai/owl#"))
    g.bind("gdpr",     rdflib.Namespace("https://w3id.org/dpv/legal/eu/gdpr/owl#"))
    g.bind("aiact",    rdflib.Namespace("https://w3id.org/dpv/legal/eu/aiact/owl#"))
    g.serialize(destination=OUT_ONTOLOGY, format="xml")
    os.remove(tmp)
    print(f"  {OUT_ONTOLOGY}  ({len(g)} triples)\n")
    return len(g)


def main():
    if not GROQ_API_KEY:
        sys.exit("GROQ_API_KEY not set")
    if not os.path.exists(CHUNKS_JSON):
        sys.exit(f"{CHUNKS_JSON} not found — run parser.py first")

    os.makedirs(OUT_DIR, exist_ok=True)

    with open(CHUNKS_JSON, encoding="utf-8") as f:
        chunks = json.load(f)

    # deduplicate chunk_ids before processing (parser edge cases)
    seen_cids, deduped_chunks = set(), []
    for c in chunks:
        if c["chunk_id"] not in seen_cids:
            seen_cids.add(c["chunk_id"])
            deduped_chunks.append(c)
    if len(deduped_chunks) < len(chunks):
        print(f"Dropped {len(chunks)-len(deduped_chunks)} duplicate chunk_ids from input")
    chunks = deduped_chunks

    regs = sorted({c["regulation"] for c in chunks})
    print(f"{len(chunks)} chunks loaded  ({', '.join(regs)})\n")

    class_index = load_dpv()
    all_dpv   = {c.name: c for c in default_world.classes()}
    all_props = {p.name: p for p in default_world.search(type=ObjectProperty)}
    client    = Groq(api_key=GROQ_API_KEY)

    # sanitize candidate names immediately after extraction
    step1_results = step1(chunks, [e["local_name"] for e in class_index], client)
    for r in step1_results:
        for cand in r["candidates"]:
            cand["candidate_name"]       = sanitize(cand.get("candidate_name", ""))
            cand["suggested_dpv_parent"] = sanitize(cand.get("suggested_dpv_parent", ""))
    with open(OUT_CANDIDATES, "w", encoding="utf-8") as f:
        json.dump(step1_results, f, indent=2, ensure_ascii=False)

    aligned = step2(step1_results, class_index, client)
    with open(OUT_ALIGNMENT, "w", encoding="utf-8") as f:
        json.dump(aligned, f, indent=2, ensure_ascii=False)

    onto    = get_ontology(FALLRISK_NS)
    created = step3(aligned, class_index, onto, all_props, all_dpv)
    with open(OUT_CLASSES, "w", encoding="utf-8") as f:
        json.dump(created, f, indent=2, ensure_ascii=False)

    unsat      = step4()
    dedup_flags= step5(created, aligned)
    with open(OUT_DEDUP, "w", encoding="utf-8") as f:
        json.dump(dedup_flags, f, indent=2, ensure_ascii=False)

    n_triples = step6(onto)

    merged_n = sum(1 for c in created if c.get("merged_into"))
    actual_n = len(created) - merged_n
    unres_n  = sum(1 for c in created if c["parent_resolved"] is False)
    restr_n  = sum(1 for c in created if not c.get("merged_into") and c.get("restrictions_applied"))
    reas_str = ("PASS" if unsat == [] else f"FAIL ({len(unsat)})" if unsat else "could not run")

    with open(OUT_LOG, "w", encoding="utf-8") as f:
        f.write(f"""# Phase 1 Build Log

- Regulations: {', '.join(regs)}
- Chunks: {len(chunks)}
- Raw candidates: {sum(len(r['candidates']) for r in step1_results)}
- Failed extractions: {sum(1 for r in step1_results if r.get('extraction_failed'))}
- Genuinely new: {sum(1 for c in aligned if c['alignment']['decision']=='genuinely_new')}
- Classes created: {actual_n}  ({merged_n} case-fold dupes)
- Thing-fallbacks: {unres_n}  -> run phase1_cleanup.py
- With restrictions: {restr_n}
- Reasoner: {reas_str}
- Dedup pairs: {len(dedup_flags)}
- Triples: {n_triples}
- Output: {OUT_ONTOLOGY}
""")

    print(f"classes: {actual_n}  |  Thing-fallbacks: {unres_n}  "
          f"|  restrictions: {restr_n}  |  dedup: {len(dedup_flags)}")
    print(f"reasoner: {reas_str}")
    print(f"output:   {OUT_ONTOLOGY}")
    print(f"\nnext: run phase1_cleanup.py")


if __name__ == "__main__":
    main()