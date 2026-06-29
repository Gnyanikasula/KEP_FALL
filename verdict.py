# SHIELD v1 - Stage 6: Hybrid Retrieval + LLM Verdict


import os
import sys
import re
import json
import time
from typing import Optional, List, Literal
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator, ValidationError

from neo4j import GraphDatabase
import chromadb
from sentence_transformers import SentenceTransformer

from route import understand_query, QueryPayload

load_dotenv()

#  Config 
MODEL          = "meta-llama/llama-4-scout-17b-16e-instruct"
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
CHROMA_PATH    = "./chroma_db"
COLLECTION     = "regulations"
# FIXED: must match the model used in rag.py to build the index.
# Querying with a different model compares incompatible vector spaces.
EMBED_MODEL    = "nomic-ai/nomic-embed-text-v1.5"
# EMBED_MODEL = "jinaai/jina-embeddings-v2-base-en"
MAX_RETRIES    = 2
RETRY_DELAY    = 2
_HISTORY_TURNS = int(os.getenv("SHIELD_HISTORY_TURNS", "6"))  # 6 msgs = 3 exchanges
GENERIC_WORDS  = {"data", "personal", "information", "the", "a", "an"}


# Lazy singletons
_DRIVER         = None
_COLLECTION     = None
_EMBED_INSTANCE = None


def _driver():
    global _DRIVER
    if _DRIVER is None:
        _DRIVER = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _DRIVER


def _collection():
    global _COLLECTION
    if _COLLECTION is None:
        _COLLECTION = chromadb.PersistentClient(path=CHROMA_PATH).get_collection(COLLECTION)
    return _COLLECTION


def _embed_model():
    global _EMBED_INSTANCE
    if _EMBED_INSTANCE is None:
        _EMBED_INSTANCE = SentenceTransformer(EMBED_MODEL, trust_remote_code=True)
    return _EMBED_INSTANCE

# def _embed_model():
#     global _EMBED_INSTANCE
#     if _EMBED_INSTANCE is None:
#         _EMBED_INSTANCE = SentenceTransformer(
#             EMBED_MODEL, trust_remote_code=True)
#     return _EMBED_INSTANCE
def _embed(text: str) -> list[float]:
    """Embed a single query string with nomic's required search_query prefix."""
    vec = _embed_model().encode(
        [f"search_query: {text}"], normalize_embeddings=True
    )
    return vec[0].tolist()
# def _embed(text: str) -> list[float]:
#     return _embed_model().encode(
#         [text], normalize_embeddings=True
#     )[0].tolist()


# Verdict schema
class Verdict(BaseModel):
    verdict:    Literal["Allowed", "Conditionally Allowed", "Prohibited",
                        "Unclear", "Informational", "Out of Scope"]
    rules:      List[str]     
    reasoning:  str              
    conditions: List[str] = []                       
    confidence: int              

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v: int) -> int:
        return max(0, min(100, int(v)))


# Legal term expansion 
# Bridges user language ("health data") to exact regulatory vocabulary
# ("data concerning health", "special categories") so RAG finds the right chunks
# even when the user's phrasing doesn't match the regulation's wording.
_LEGAL_TERM_MAP: dict[str, list[str]] = {
    "health data":          ["data concerning health", "special categories",
                             "clinical data", "medical data", "health information"],
    "medical data":         ["data concerning health", "special categories",
                             "clinical data", "health status"],
    "personal data":        ["personal data", "data subject", "natural person",
                             "identifiable person"],
    "biometric data":       ["biometric data", "facial images", "dactyloscopic",
                             "unique identification"],
    "genetic data":         ["genetic data", "inherited characteristics",
                             "biological sample"],
    "consent":              ["explicit consent", "freely given", "specific informed",
                             "unambiguous indication", "withdrawal of consent"],
    "lawful basis":         ["lawful basis", "legal basis", "Article 6",
                             "legitimate interests", "contractual necessity",
                             "legal obligation", "vital interests", "public task"],
    "explicit consent":     ["explicit consent", "Article 9(2)(a)",
                             "freely given specific informed unambiguous"],
    "right to erasure":     ["right to erasure", "right to be forgotten",
                             "Article 17", "erase personal data"],
    "right of access":      ["right of access", "Article 15", "access to data"],
    "data portability":     ["data portability", "Article 20", "structured format"],
    "automated decisions":  ["automated processing", "solely automated",
                             "legal effects", "profiling", "Article 22"],
    "profiling":            ["profiling", "automated processing", "evaluate aspects",
                             "predict behaviour", "Article 22"],
    "data minimisation":    ["data minimisation", "adequate relevant limited",
                             "Article 5(1)(c)", "minimum necessary"],
    "purpose limitation":   ["purpose limitation", "Article 5(1)(b)",
                             "specified explicit legitimate purposes"],
    "storage limitation":   ["storage limitation", "Article 5(1)(e)",
                             "no longer than necessary", "retention period"],
    "transparency":         ["transparency", "Article 5(1)(a)", "transparent manner",
                             "clear plain language"],
    "privacy by design":    ["data protection by design", "Article 25",
                             "privacy by design", "pseudonymisation"],
    "dpia":                 ["data protection impact assessment", "Article 35",
                             "DPIA", "high risk processing", "prior consultation"],
    "data breach":          ["personal data breach", "Article 33", "Article 34",
                             "notification", "72 hours", "supervisory authority"],
    "data transfer":        ["transfer personal data", "third country",
                             "adequacy decision", "Article 44", "Article 45"],
    "high risk ai":         ["high-risk AI system", "Annex III", "Article 6",
                             "safety component", "significant harm",
                             "fundamental rights", "Chapter III Section 2"],
    "prohibited ai":        ["prohibited AI practices", "Article 5",
                             "subliminal techniques", "social scoring",
                             "real-time biometric", "manipulation"],
    "general purpose ai":   ["general-purpose AI model", "GPAI", "Article 51",
                             "systemic risk"],
    "human oversight":      ["human oversight", "Article 14", "natural person",
                             "monitor functioning", "override halt"],
    "transparency ai":      ["transparency obligations", "Article 50", "Article 13",
                             "instructions for use", "technical documentation"],
    "technical documentation": ["technical documentation", "Annex IV", "Article 11",
                                "general description", "development process"],
    "risk management":      ["risk management system", "Article 9",
                             "identify analyse estimate", "residual risk"],
    "post market monitoring": ["post-market monitoring", "Article 72",
                               "market surveillance", "serious incident"],
    "medical device":       ["medical device", "Article 2(1)", "intended purpose",
                             "diagnosis prevention monitoring"],
    "software medical device": ["software", "SaMD", "Recital 19",
                                "medical purpose", "standalone software",
                                "Rule 11", "Annex VIII"],
    "device classification":["device classification", "Annex VIII", "Rule 11",
                             "Class IIa", "Class IIb", "Class III"],
    "clinical evaluation":  ["clinical evaluation", "Article 61", "Annex XIV",
                             "clinical data", "clinical evidence"],
    "manufacturer obligations": ["manufacturer", "Article 10",
                                 "quality management system", "post-market surveillance",
                                 "technical documentation"],
    "uk mdr":               ["UK MDR 2002", "SI 2002/618", "MHRA", "Great Britain",
                             "UK Conformity Assessed", "UKCA"],
    "controller":           ["controller", "Article 4(7)", "determines purposes"],
    "processor":            ["processor", "Article 4(8)", "processes on behalf",
                             "Article 28", "data processing agreement"],
    "anonymisation":        ["anonymisation", "pseudonymisation", "Article 4(5)",
                             "re-identification", "cannot be attributed"],
        # Extra retrieval terms
    "location data":        ["location data", "movements", "tracking"],
    "financial data":       ["financial interests", "economic situation",
                             "creditworthiness"],
    "right to object":      ["right to object", "Article 21", "direct marketing",
                             "legitimate grounds"],
    "accuracy":             ["accuracy", "Article 5(1)(d)", "kept up to date",
                             "inaccurate data rectified"],
    "accountability":       ["accountability", "Article 5(2)",
                             "demonstrate compliance", "controller responsible"],
    "integrity confidentiality": ["integrity confidentiality", "Article 5(1)(f)",
                                  "appropriate security", "encryption",
                                  "unauthorised access"],
    "data protection officer": ["data protection officer", "DPO", "Article 37",
                                "Article 38", "Article 39"],
    "security":             ["security of processing", "Article 32",
                             "technical organisational measures", "encryption",
                             "pseudonymisation", "confidentiality integrity"],
    "conformity assessment": ["conformity assessment", "Article 43",
                              "notified body", "EU declaration of conformity",
                              "Article 47", "CE marking"],
    "ce marking":           ["CE marking", "conformity assessment",
                             "notified body", "Article 52",
                             "declaration of conformity"],
    "vigilance":            ["vigilance", "Article 87", "serious incident",
                             "field safety corrective action", "FSCA",
                             "competent authority notification"],
    "unique device identifier": ["unique device identifier", "UDI",
                                 "Article 27", "EUDAMED", "traceability"],
    "mhra":                 ["MHRA", "UK MDR 2002", "competent authority",
                             "Great Britain market"],
    "supervisory authority": ["supervisory authority", "data protection authority",
                              "ICO", "CNIL", "Article 51", "Article 55"],
    "legitimate interests": ["legitimate interests", "Article 6(1)(f)",
                             "balancing test", "override interests"],
    # DUAA 2025 terms
    "duaa":                 ["Data Use and Access Act", "DUAA 2025", "s.80",
                             "Article 22A", "Article 22B", "Article 22C",
                             "Article 22D", "Schedule 6"],
    "automated significant decision": ["significant decision", "solely automated",
                                       "legal effect", "similarly significant effect",
                                       "opt out", "human review", "s.80 Art22A",
                                       "Art22B restrictions", "Art22C safeguards"],
    "data intermediary":    ["data intermediary", "data sharing", "Schedule 6",
                             "recognised data altruism organisation",
                             "data intermediary services"],
    "uk automated decisions": ["automated processing significant", "opt-out right",
                               "human review request", "Article 22A", "Article 22B"],
}


def _expand_legal_terms(text: str) -> list[str]:
    """Return expanded regulatory vocabulary for any known concept in the text."""
    text_lower = text.lower()
    expansions: list[str] = []
    seen: set[str] = set()
    for user_term, legal_synonyms in _LEGAL_TERM_MAP.items():
        if any(w in text_lower for w in user_term.split()):
            for s in legal_synonyms:
                if s not in seen:
                    seen.add(s)
                    expansions.append(s)
    return expansions


# Phase 3: KG retrieval helpers

# Retrieval: Knowledge Graph
def _kg_keyword(text: str) -> str:
    """Strip generic stop-words and return the first meaningful keyword."""
    words = [w for w in text.lower().split() if w not in GENERIC_WORDS]
    return words[0] if words else text.lower().split()[0]


def _article_id_to_citation(article_id: str) -> str:
    """
    Convert Phase 2 article_id format to human-readable citation string.
    Examples:
      'GDPR__Art6'               → 'GDPR, Article 6'
      'EU AI Act__Art5'          → 'EU AI Act, Article 5'
      'EU AI Act__Art6_Para1_a'  → 'EU AI Act, Article 6(1)(a)'
    """
    if not article_id:
        return ""
    parts = article_id.split("__", 1)
    if len(parts) != 2:
        return article_id
    reg, art = parts
    # "Art6" → "Article 6"
    art = re.sub(r"^Art(\d+)", r"Article \1", art)
    # "_Para1" → "(1)"
    art = re.sub(r"_Para(\d+)", r"(\1)", art)
    # remaining "_a" / "_b" sub-points → "(a)" / "(b)"
    art = re.sub(r"_([a-z])$", r"(\1)", art)
    # anything else with underscores → spaces
    art = art.replace("_", " ")
    return f"{reg}, {art}"


def kg_retrieve(payload: QueryPayload) -> List[dict]:
    """
    Phase 3 KG retrieval — queries the Phase 2 AuraDB schema:
      Node  :Concept  { label, uri, typed, source_reg }
      Edge  :REL      { predicate, predicate_uri, regulation,
                        article_id, chunk_ids, confidence }

    Strategy:
      1. Build keyword list from data_type + system_type + topic
      2. Match :Concept nodes whose label OR uri contains any keyword
      3. Traverse all :REL edges from those anchor nodes
      4. Prefer typed=true nodes (ontology-grounded) via ORDER BY
      5. Return structured rows the LLM can cite directly
    """
    # 1. Build keyword list
    keyword_sources = [
        payload.data_type,
        payload.system_type,
        payload.topic,
    ]
    keywords = list({
        _kg_keyword(src)
        for src in keyword_sources
        if src  # skip None
    })
    if not keywords:
        return []

    # 2 + 3. Cypher: anchor on keyword, traverse :REL
    # Two passes in one query:
    #   Pass A – outgoing edges from anchor (anchor IS the subject)
    #   Pass B – incoming edges to anchor   (anchor IS the object)
    # This catches both "HealthData --hasLegalBasis--> Consent"
    # and "Processing --appliesTo--> HealthData" patterns.
    cypher = """
        // Pass A — anchor is the subject
        MATCH (s:Concept)-[r:REL]->(o:Concept)
        WHERE any(kw IN $keywords
                  WHERE toLower(s.label) CONTAINS kw
                     OR (s.uri IS NOT NULL AND toLower(s.uri) CONTAINS kw))
        RETURN s.label        AS subject,
               s.uri          AS subject_uri,
               s.typed        AS typed,
               r.predicate    AS predicate,
               o.label        AS object,
               o.uri          AS object_uri,
               r.regulation   AS regulation,
               r.article_id   AS article_id,
               r.chunk_ids    AS chunk_ids,
               r.confidence   AS confidence
        ORDER BY r.confidence DESC, s.typed DESC
        LIMIT 30

        UNION

        // Pass B — anchor is the object
        MATCH (s:Concept)-[r:REL]->(o:Concept)
        WHERE any(kw IN $keywords
                  WHERE toLower(o.label) CONTAINS kw
                     OR (o.uri IS NOT NULL AND toLower(o.uri) CONTAINS kw))
        RETURN s.label        AS subject,
               s.uri          AS subject_uri,
               s.typed        AS typed,
               r.predicate    AS predicate,
               o.label        AS object,
               o.uri          AS object_uri,
               r.regulation   AS regulation,
               r.article_id   AS article_id,
               r.chunk_ids    AS chunk_ids,
               r.confidence   AS confidence
        ORDER BY r.confidence DESC, s.typed DESC
        LIMIT 20
    """

    try:
        recs = _driver().execute_query(
            cypher, keywords=keywords, database_=NEO4J_DATABASE
        ).records
    except Exception as exc:
        # Never hard-fail — RAG still runs if KG is unavailable
        log.warning("kg_retrieve failed: %s", exc) if (log := _get_log()) else None
        return []

    # --- 4. Deduplicate + format -----------------------------------------
    seen, results = set(), []
    for r in recs:
        key = f"{r['subject']}|{r['predicate']}|{r['object']}"
        if key in seen:
            continue
        seen.add(key)
        row = dict(r)
        # Add human-readable citation so build_context and the LLM can cite it
        row["citation"] = _article_id_to_citation(r["article_id"] or "")
        results.append(row)

    return results


def _get_log():
    """Return a logger without a module-level import dependency."""
    try:
        import logging
        return logging.getLogger(__name__)
    except Exception:
        return None


# Retrieval: Vector Store
def rag_retrieve(payload: QueryPayload, k: int = 4) -> List[dict]:
    """Multi-angle RAG retrieval covering GDPR, EU AI Act, MDR, and DUAA 2025.

    Query construction rules:
    - Base queries anchor on the specific compliance action (store/share/deploy),
      NOT on generic data type strings — this stops Art16/Art18 (data subject
      rights) from crowding out Art6/Art9 (lawful basis) for storage questions.
    - Purpose-driven queries fire the exact legal path (Art9(2)(j) for training,
      Art9(2)(h) for direct care, DUAA s.80 for significant automated decisions).
    - Deployment context queries add sector-specific obligations.
    - Legal term expansion bridges user vocabulary to regulatory text.
    """
    col = _collection()
    dt   = payload.data_type          or "personal data"
    st   = payload.system_type        or "AI system"
    act  = payload.action             or "process"
    purp = payload.purpose            or ""
    ctx  = payload.deployment_context or ""
    jur  = payload.jurisdiction       or ""

    # Base queries — action-specific, avoids data-subject-rights articles
    # "store" / "share" → lawful basis + special category, not erasure/rectification
    base_queries = [
        f"{dt} {act} lawful basis legal basis",
        f"{dt} special category explicit consent Article 9",
        f"{st} high-risk AI obligations Article 6 Annex III",
        f"{dt} {act} controller processor obligations",
    ]

    # Purpose-driven queries
    purpose_queries = []
    if purp:
        purpose_queries.append(f"{dt} {purp} lawful basis GDPR Article 9")
        if "training" in purp.lower() or "research" in purp.lower():
            purpose_queries.append(
                "health data AI model training research statistical purpose "
                "Article 9(2)(j) scientific research exemption"
            )
        if "care" in purp.lower() or "clinical" in purp.lower():
            purpose_queries.append(
                "health data direct patient care clinical decision support "
                "Article 9(2)(h) healthcare professional"
            )
        if "workplace" in purp.lower() or "monitoring" in purp.lower():
            purpose_queries.append(
                "emotion recognition workplace prohibited AI practices Article 5"
            )
        if "hiring" in purp.lower() or "screening" in purp.lower():
            purpose_queries.append(
                "automated CV scoring employment high-risk AI Annex III Article 22"
            )
        if "loan" in purp.lower() or "credit" in purp.lower():
            purpose_queries.append(
                "automated credit loan decision GDPR Article 22 human oversight"
            )
        if "significant" in purp.lower() or "automated" in purp.lower():
            purpose_queries.append(
                "automated significant decision legal effect opt-out "
                "DUAA 2025 Article 22A 22B 22C safeguards human review"
            )

    # Deployment context queries
    context_queries = []
    if ctx:
        if "hospital" in ctx.lower() or "clinical" in ctx.lower():
            context_queries.extend([
                f"medical device software {st} MDR clinical evaluation Article 61",
                f"{st} manufacturer obligations MDR conformity assessment Article 10",
            ])
        if "workplace" in ctx.lower():
            context_queries.append(
                "emotion recognition workplace prohibition EU AI Act Article 5"
            )
        if "public" in ctx.lower():
            context_queries.append(
                "real-time biometric identification public space prohibited Article 5"
            )
        if "financial" in ctx.lower():
            context_queries.append(
                "automated decision loan credit GDPR Article 22 human oversight"
            )
    else:
        # No context — include MDR as a secondary path, weighted lower
        context_queries.extend([
            f"medical device software {st} MDR Article 2 definition",
            f"{st} clinical evaluation MDR Article 61",
        ])

    # DUAA 2025 — fire when jurisdiction is UK or purpose involves automated decisions
    duaa_queries = []
    if "uk" in jur.lower() or "significant" in purp.lower() or "automated" in act.lower():
        duaa_queries.append(
            "automated significant decision DUAA 2025 Article 22A 22B opt-out "
            "human review safeguards Schedule 6"
        )
    if "uk" in jur.lower():
        duaa_queries.append(
            "UK MDR 2002 conformity assessment MHRA Part 4A post-market"
        )

    # Legal term expansions — cap to avoid context overflow
    expansions = (
        _expand_legal_terms(dt)[:3]
        + _expand_legal_terms(st)[:3]
        + _expand_legal_terms(purp)[:2]
    )

    queries = base_queries + purpose_queries + context_queries + duaa_queries + expansions

    out, seen = [], set()
    for q in queries:
        res = col.query(query_embeddings=[_embed(q)], n_results=k)
        for cid, doc, meta in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0]
        ):
            if cid not in seen:
                seen.add(cid)
                out.append({
                    "chunk_id": cid,
                    "citation": meta.get("citation", cid),
                    "text":     doc,
                    "type":     meta.get("type", ""),
                })
    return out


def rag_knowledge(payload: QueryPayload, k: int = 6) -> List[dict]:
    """RAG retrieval for knowledge/explanation questions (no permit/deny verdict)."""
    col = _collection()
    q = " ".join(filter(None, [payload.topic, payload.system_type]))
    expansions = _expand_legal_terms(q)
    queries = [
        q or "regulation",
        f"{q} purpose intent recital" if q else "recital purpose intent",
        "technical documentation general description AI system intended purpose",
    ] + expansions[:6]

    out, seen = [], set()
    for query in queries:
        res = col.query(query_embeddings=[_embed(query)], n_results=k)
        for cid, doc, meta in zip(res["ids"][0], res["documents"][0], res["metadatas"][0]):
            if cid not in seen:
                seen.add(cid)
                out.append({"chunk_id": cid,
                            "citation": meta.get("citation", cid),
                            "text": doc,
                            "type": meta.get("type", "")})
    return out


def _rag_retrieve_combined(payloads: list[QueryPayload], k: int = 3) -> list[dict]:
    """Merge RAG results across all session compliance payloads.
    Used for summary requests - gives LLM context covering the entire session.
    k is smaller per payload to prevent context overflow."""
    out, seen = [], set()
    for p in payloads:
        chunks = rag_knowledge(p, k=k) if p.intent == "knowledge" else rag_retrieve(p, k=k)
        for c in chunks:
            if c["chunk_id"] not in seen:
                seen.add(c["chunk_id"])
                out.append(c)
    return out


# Context builder
def build_context(kg: List[dict], rag: List[dict]) -> str:
    """
    Merge KG structured rules + RAG excerpts into one context block.

    Phase 3 KG row shape (Phase 2 schema):
      subject, subject_uri, typed, predicate, object, object_uri,
      regulation, article_id, chunk_ids, confidence, citation (added by kg_retrieve)
    """
    lines = ["## STRUCTURED RULES (knowledge graph)"]
    if kg:
        for r in kg:
            subj    = r.get("subject",   "?")
            pred    = r.get("predicate", "?")
            obj     = r.get("object",    "?")
            cite    = r.get("citation",  "")   # human-readable, e.g. "GDPR, Article 6"
            chunks  = r.get("chunk_ids") or []
            typed   = r.get("typed",     False)

            # First two source chunk IDs give the evaluator a trace back to raw text
            chunk_ref = f" [chunks: {', '.join(chunks[:2])}]" if chunks else ""
            typed_tag = "" if typed else " ⚠ untyped"

            lines.append(
                f"- {subj} --[{pred}]--> {obj}"
                f"{(' (' + cite + ')') if cite else ''}"
                f"{chunk_ref}{typed_tag}"
            )
    else:
        lines.append("- (no structured rules matched — KG returned 0 results)")

    lines.append("\n## REGULATION EXCERPTS (verbatim, for grounding)")
    for c in rag:
        excerpt = c["text"][:3000].replace("\n", " ")
        lines.append(f"### {c['citation']}\n{excerpt}")
    return "\n".join(lines)


# LLM system prompts
SYSTEM = """You are a regulatory compliance engine covering GDPR, the EU AI Act,
medical-device regulation (EU MDR 2017/745 and UK MDR 2002), and the
Data (Use and Access) Act 2025 (DUAA 2025).
Decide whether the user's described activity is Allowed, Conditionally Allowed,
Prohibited, or Unclear.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE GATE (check FIRST)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Assess compliance ONLY for: processing personal data, building/deploying AI systems,
placing/using medical devices, and automated significant decisions under the
regulations above.
Unrelated questions → "Unclear", empty rules, explain in reasoning.
Do NOT force a data-protection analysis onto unrelated questions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERPRETING THE PARSED PAYLOAD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The PARSED field contains structured intent extracted from the question. Use it:

purpose - WHY the data/system is used. This determines which GDPR Art.9(2)
exception applies and whether MDR or DUAA applies:
  "direct patient care"              → Art.9(2)(h), MDR likely applies in hospital
  "AI model training"                → Art.9(2)(j) research exemption
  "workplace monitoring"             → EU AI Act Art.5 prohibition may fire
  "loan / credit assessment"         → GDPR Art.22 automated decision rules apply
  "automated significant decision"   → DUAA 2025 s.80 Art.22A-22C safeguards apply

deployment_context - WHERE the system operates:
  "hospital"      → MDR conformity assessment obligations very likely required
  "workplace"     → emotion recognition AI is PROHIBITED under EU AI Act Art.5
  "public space"  → real-time biometric AI is PROHIBITED under EU AI Act Art.5
  "financial services" → GDPR Art.22 automated decisions likely apply
  null/other      → do NOT assume MDR applies without explicit medical context

jurisdiction - WHERE the operator is based:
  "UK"    → UK MDR 2002 applies instead of EU MDR; DUAA 2025 may apply
  "EU"    → EU MDR 2017/745 applies; DUAA does not apply
  "EU+UK" → both MDR regimes may apply; consider DUAA for automated decisions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL DISTINCTION - PROHIBITS IN CONTEXT vs PROHIBITED ACTIVITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The CONTEXT may show rules like "Health Data [PROHIBITS] processing without lawful basis".
This means the REGULATION prohibits processing WITHOUT meeting conditions - NOT that
the activity itself is prohibited. If conditions can be met (consent, legal obligation, etc.),
the verdict is "Conditionally Allowed", not "Prohibited".
Reserve "Prohibited" ONLY for activities explicitly banned regardless of conditions:
  - EU AI Act Art.5: real-time biometric ID in public spaces
  - EU AI Act Art.5: emotion recognition in workplace/education
  - EU AI Act Art.5: social scoring by public authorities
  - EU AI Act Art.5: subliminal manipulation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANALYSIS RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Base answer ONLY on the CONTEXT. Do NOT use outside knowledge.
- STRUCTURED RULES section contains typed triples from the knowledge graph.
  Each rule is formatted as: Subject --[predicate]--> Object (Regulation, Article N)
  Use the article citation in parentheses directly in your "rules" array,
  e.g. "GDPR, Article 9" — do not invent article numbers.
- REGULATION EXCERPTS section contains verbatim regulatory text for grounding.
  Cite the article header shown above each excerpt.
- If context is insufficient → "Unclear".
- Consider EVERY applicable dimension the context supports:
  (1) GDPR — lawful basis, special-category data, automated decisions
  (2) EU AI Act — prohibited practices (Art.5), high-risk classification (Art.6),
      obligations (Arts.9-15), transparency (Art.13)
  (3) MDR — ONLY when deployment_context is "hospital" or system is clearly for
      medical diagnosis/treatment. If jurisdiction="UK" apply UK MDR 2002;
      if "EU" apply EU MDR 2017/745; if "EU+UK" consider both.
  (4) DUAA 2025 — apply when jurisdiction="UK" AND the system makes automated
      decisions with significant effects on individuals (s.80 Art.22A-22C):
      opt-out rights, human review, safeguards, Schedule 6 exemptions.
      Do NOT apply DUAA to EU-only scenarios.
- ⚠ untyped in a STRUCTURED RULE means it was extracted organically — weight
  slightly lower than typed rules.
- Recitals in context explain legislative intent — cite the operative article.
- Do NOT invent scenarios the user did not describe.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONDITIONS (when Conditionally Allowed)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When verdict is "Conditionally Allowed", populate "conditions" with a numbered
list of concrete steps the operator MUST take. Each condition must cite the
article that requires it. Be specific - not "comply with GDPR" but
"Obtain explicit consent from data subjects (GDPR, Art.9(2)(a))".
For all other verdicts, "conditions" must be [].

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIDENCE CALIBRATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
90-100: context directly and fully answers the question across all relevant dimensions
70-85:  context partially covers it, some dimensions missing
50-69:  context is thin or question extends beyond what was provided
<50:    significant gaps, verdict is an estimate

Multi-regulation questions (GDPR + AI Act + MDR + DUAA) rarely exceed 85 unless
all relevant dimensions are fully covered in context. Do NOT default to 80 or 100.

Return STRICT JSON only - no prose, no markdown.
EXACT FIELD TYPES - do not deviate:
  "verdict"    : string - exactly one of the six verdict values
  "rules"      : array of strings - citation strings only, e.g. ["GDPR, Article 9"]
  "reasoning"  : string - ONE paragraph of prose. NEVER a list or array.
  "conditions" : array of strings - specific steps when Conditionally Allowed, else []
  "confidence" : integer - 0 to 100

Example shape (values are illustrative only):
{
  "verdict": "Conditionally Allowed",
  "rules": ["GDPR, Article 9", "EU AI Act, Article 6"],
  "reasoning": "The system processes special category health data and must meet strict conditions before deployment.",
  "conditions": ["Obtain explicit consent (GDPR, Art.9(2)(a))", "Conduct DPIA (GDPR, Art.35)"],
  "confidence": 82
}"""

SYSTEM_KNOWLEDGE = """You are a regulatory information assistant for GDPR, the EU AI Act,
the MDR (EU MDR 2017/745 and UK MDR 2002), and the Data (Use and Access) Act 2025 (DUAA 2025).
The user is asking you to EXPLAIN or DEFINE a rule or concept -
this is informational, NOT a permit/deny decision.

RULES:
- Answer using ONLY the provided CONTEXT. Do NOT use outside knowledge.
- Cite the specific articles you used in "rules".
- Keep "verdict" exactly "Informational".
- "conditions" must always be [] for knowledge responses.
- If context does not fully cover the question, say so clearly in reasoning,
  explain what IS known, and suggest consulting the official regulation text.
  Set confidence below 60.
- If the user asks for a list, bullet points, or numbered format, structure
  the "reasoning" field accordingly.
- If the user asks for "all", "every", "complete", "full", or "exhaustive"
  requirements, provide a complete structured answer based on all relevant
  CONTEXT excerpts, not just the first matching article.
- Preserve nested legal structure where the CONTEXT contains chapters,
  sections, paragraphs, points, sub-points, or numbered duties. For example,
  if a rule has Article → paragraph → point, keep that hierarchy clear in
  the reasoning.
- When multiple regulations are relevant, group the explanation by regulation
  where possible, for example GDPR first, then EU AI Act, then MDR.
- Context may include recital excerpts - use them to explain legislative intent
  alongside the operative articles.
- Calibrate confidence honestly:
  90-100: context directly and fully answers the question
  70-85:  partially covered
  Below 70: context is thin or question goes beyond what is provided
  Do NOT default to 80 every time.

Return STRICT JSON only - no prose, no markdown.
EXACT FIELD TYPES:
  "verdict"    : string - always exactly "Informational"
  "rules"      : array of strings
  "reasoning"  : string - ONE paragraph or numbered prose. NEVER a list or array.
  "conditions" : array - always [] for knowledge responses
  "confidence" : integer - 0 to 100

Example shape:
{
  "verdict": "Informational",
  "rules": ["EU AI Act, Article 6"],
  "reasoning": "High-risk AI systems are those listed in Annex III or that serve as safety components.",
  "conditions": [],
  "confidence": 78
}"""

# Appended to system prompt when conversation history is present.
# Tells the LLM to use prior turns for continuity - this is the core of
# why history makes the system smarter, not just stateful.
_SYSTEM_MEMORY_SUFFIX = """

CONVERSATION MEMORY:
You have access to the recent conversation history (user and assistant turns above).
Use it to:
- Connect the current question to earlier turns (e.g. "what does that mean?"
  refers to what you just said - do NOT ask a clarifying question).
- Avoid repeating information already given.
- If the user answers a follow-up question you asked, treat their answer as
  a continuation - do NOT re-ask the same question.
- If the user asks to reformat or list something from your previous answer,
  use YOUR PREVIOUS RESPONSE from history as the source, not just the CONTEXT.
- If the user asks for an example, always include a concrete real-world
  example in your reasoning that relates to the specific topic being discussed,
  not a generic one."""


# Unified LLM call
def _synthesize(
    system: str,
    prompt: str,
    history_msgs: list[dict] | None = None,
) -> Optional[Verdict]:
    """
    Single synthesis function for all intents. Replaces four functions:
    synthesize_verdict / _synthesize_verdict_with_history /
    synthesize_explanation / _synthesize_explanation_with_history.

    history_msgs: prior conversation turns from _build_history_messages().
    When provided, they sit between the system prompt and the current user turn
    so the LLM sees the conversation flow and can use it for continuity.
    """
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    nudge, last = "", ""
    for _ in range(1 + MAX_RETRIES):
        sys_content = system + nudge
        if history_msgs:
            messages = (
                [{"role": "system", "content": sys_content}]
                + history_msgs
                + [{"role": "user", "content": prompt}]
            )
        else:
            messages = [
                {"role": "system", "content": sys_content},
                {"role": "user",   "content": prompt},
            ]
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
            return Verdict.model_validate_json(resp.choices[0].message.content)
        except (ValidationError, json.JSONDecodeError, KeyError) as err:
            last  = f"{type(err).__name__}: {str(err)[:160]}"
            nudge = ("\n\nPrevious reply rejected: " + last +
                     ". Return ONLY valid JSON matching the schema.")
            time.sleep(RETRY_DELAY)

    print(f"[fail] synthesis failed -> {last}")
    return None


# Canned responses
def _canned_response(payload: QueryPayload) -> Optional[Verdict]:
    """
    Handle all non-retrieval intents in one place.
    Returns a Verdict immediately (no KG/RAG/LLM needed).
    Returns None if the intent requires retrieval (scenario / knowledge).

    This replaces the 7×2 if-blocks that were duplicated across analyze()
    and analyze_with_history(). One source of truth for every canned response.
    """
    match payload.intent:

        case "greeting":
            return Verdict(verdict="Informational", rules=[], confidence=100,
                           reasoning="Hi there! What are you trying to figure out today?")

        case "help":
            return Verdict(
                verdict="Informational", rules=[], confidence=100,
                reasoning=(
                    "Happy to help - what kind of question are you facing? "
                    "Is it about whether a specific system or action is permitted, "
                    "or are you trying to understand what a particular regulation requires?"
                ),
            )

        case "examples":
            return Verdict(
                verdict="Informational", rules=[], confidence=100,
                reasoning=(
                    "Here are some questions you can ask SHIELD:\n"
                    "1. Can my elderly-care assistant store fall-risk predictions and share them with caregivers?\n"
                    "2. Does a wearable fall-risk predictor need explicit consent?\n"
                    "3. Is an AI care assistant a high-risk AI system?\n"
                    "4. What human oversight is required for an AI care assistant?\n"
                    "5. Is fall-risk prediction software a medical device?\n"
                    "6. Can health data be used to train a bias-detection model?"
                ),
            )

        case "sensitive":
            return Verdict(
                verdict="Out of Scope", rules=[], confidence=100,
                reasoning=(
                    "I want to make sure you're okay. If you or someone you know "
                    "is in danger or distress, please reach out to emergency services "
                    "or a crisis support line in your country immediately.\n\n"
                    "SHIELD is a regulatory compliance tool and cannot help with "
                    "questions involving harm to people. If there is a genuine "
                    "compliance question behind what you are asking - for example, "
                    "about end-of-life care data, AI systems in palliative care, "
                    "or medical device obligations - I am here for that."
                ),
            )

        case "medical_advice":
            return Verdict(
                verdict="Out of Scope", rules=[], confidence=100,
                reasoning=(
                    "That sounds like a personal health question - and for that, "
                    "a qualified healthcare professional is the right person to ask. "
                    "If it's urgent, please contact your local emergency service.\n\n"
                    "If your question is actually about whether an AI system or medical "
                    "device is permitted to handle this kind of information under GDPR, "
                    "the EU AI Act, or MDR - that's exactly what I'm here for. "
                    "Could you tell me a bit more about what you're trying to find out?"
                ),
            )

        case "unsupported_regulation":
            return Verdict(
                verdict="Out of Scope", rules=[], confidence=100,
                reasoning=(
                    "That touches a legal area outside my current scope. "
                    "I cover GDPR, the EU AI Act, EU MDR 2017/745, UK MDR 2002, "
                    "and the Data (Use and Access) Act 2025 (DUAA 2025) — "
                    "which apply across the EU, EEA, and UK. For other "
                    "legal areas, a licensed legal professional would be the right person "
                    "to consult.\n\n"
                    "If there's a data protection, AI system, medical-device, or automated "
                    "decision-making angle to your question, I'm happy to look at that part "
                    "— just let me know."
                ),
            )

        case "clarify":
            jur = getattr(payload, "jurisdiction", None)
            jur_note = ""
            if jur and jur.startswith("other:"):
                country = jur.split(":", 1)[1]
                jur_note = (
                    f" I also noticed you mentioned {country} - SHIELD covers EU/EEA "
                    f"and UK regulations, which may still apply depending on where your "
                    f"data subjects are located."
                )
            return Verdict(
                verdict="Informational", rules=[], confidence=100,
                reasoning=(
                    "That could mean a couple of different things. Are you asking about "
                    "a personal situation - for example, what to do in a health or "
                    "medication scenario? Or are you asking whether an AI system, care "
                    "assistant, or medical device is permitted to handle this kind of "
                    "information under GDPR, the EU AI Act, or MDR?" + jur_note
                ),
            )

        case "out_of_scope":
            return Verdict(
                verdict="Out of Scope", rules=[], confidence=100,
                reasoning=(
                    "That one's outside what I'm built for. I focus on healthcare AI "
                    "and medical-device compliance - things like whether a system can "
                    "lawfully process health data, whether an AI system is high-risk, "
                    "or whether software qualifies as a medical device under EU or UK "
                    "regulation.\n\n"
                    "If your question has a data protection, AI, or medical-device "
                    "angle, feel free to rephrase it and I'll do my best. "
                    "Not sure how? Type 'give me examples' and I'll show you."
                ),
            )

        case _:
            return None  # scenario / knowledge → needs retrieval


# History helpers
def _build_history_messages(history: list[dict]) -> list[dict]:
    """
    Convert SQLite message rows to LLM message dicts.
    These go BETWEEN the system prompt and the current user turn so the LLM
    sees the conversation and can maintain continuity (the whole point of history).

    NOTE: api.py must store the payload alongside the verdict so
    _extract_last_payload() and _extract_all_payloads() can read it back.
    Add "payload": parsed to verdict_payload in api.py's /query endpoint.
    """
    msgs = []
    for row in history[-_HISTORY_TURNS:]:
        if row["role"] == "user":
            msgs.append({"role": "user", "content": row["content"]})
        else:
            v = row.get("verdict")
            text = (f"[{v['verdict']}] {v['reasoning']}"
                    if v and v.get("reasoning") else row["content"])
            msgs.append({"role": "assistant", "content": text})
    return msgs


def _extract_last_payload(history: list[dict]) -> Optional[QueryPayload]:
    """Return the most recent compliance payload stored in history.
    Used for vague follow-ups ('explain that') - retrieval uses the
    previous topic rather than trying to retrieve on 'explain that'."""
    for m in reversed(history):
        if m["role"] == "assistant" and m.get("verdict"):
            stored = m["verdict"].get("payload")
            if stored and stored.get("intent") in ("scenario", "knowledge"):
                try:
                    return QueryPayload(**stored)
                except Exception:
                    continue
    return None


def _extract_all_payloads(history: list[dict]) -> list[QueryPayload]:
    """Collect all compliance payloads from the session - used for summary requests."""
    payloads, seen_keys = [], set()
    for m in history:
        if m["role"] == "assistant" and m.get("verdict"):
            stored = m["verdict"].get("payload")
            if stored and stored.get("intent") in ("scenario", "knowledge"):
                key = f"{stored.get('topic','')}|{stored.get('data_type','')}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    try:
                        payloads.append(QueryPayload(**stored))
                    except Exception:
                        continue
    return payloads


# Retrieval routing helpers─
_VAGUE_PATTERNS = [
    r"^(explain|clarify|elaborate|describe)\s*(that|this|it|more|further)?\.?$",
    r"^(what does that mean|what do you mean|i don't understand)\.?$",
    r"^(tell me more|give me more|more details|more information)\.?$",
    r"^in simple(r)? terms\.?$",
    r"^in plain (english|language)\.?$",
    r"^(list (that|it|them|those)|put it in a list|list format|in list format)\.?$",
    r"^(the \d+(st|nd|rd|th) one|option \d|choice \d)\.?$",
    r"^(yes|no|okay|ok|sure|go ahead|proceed|continue)\.?$",
    r"^(what about|how about|and (what|how) about)\.?$",
    r"^(can you give (me )?(an? )?(example|more)).*$",
    r"^simply put\.?$",
    r"^(explain this|explain it|explain more)\.?$",
    r"^(make it clearer|make this clearer)\.?$",
    r"^(make it shorter|shorter|summarise that|summarize that)\.?$",
    r"^(put it in points|give it in points|points please)\.?$",
    r"^(give example|give an example|example please)\.?$",
    r"^(why|how so|why is that)\.?$",
]

_SUMMARY_PATTERNS = [
    r".*(summar(y|ise|ize)|overview|recap|wrap up|put it all together).*",
    r".*(everything (we|you) (discussed|covered|talked about)).*",
    r".*(all of (this|that|the above)).*",
    r".*(combine|consolidate|bring it all together).*",
    r".*(all (the )?regulations? (discussed|mentioned|covered)).*",
    r".*(give me an example.*(cover|showing|for all|across all)).*",
    r".*(bullet points?.*(all|everything|summary|overview)).*",
    r".*(list.*(all|everything|summary|overview)).*",
    r".*(show.*(all|everything|summary|overview)).*",
    r".*(what have we discussed).*",
    r".*(what did we cover).*",
]


def _is_vague_followup(question: str) -> bool:
    q = question.strip().lower()
    return any(re.match(p, q) for p in _VAGUE_PATTERNS)


def _is_summary_request(question: str) -> bool:
    q = question.strip().lower()
    return any(re.search(p, q) for p in _SUMMARY_PATTERNS)


def _route(question: str, history: list[dict] | None) -> Optional[QueryPayload]:
    """
    Classify intent. When history exists, prepend recent context so follow-up
    questions like 'what does that mean?' route correctly instead of firing
    the clarify handler.
    """
    if not history or len(history) < 2:
        return understand_query(question)

    ctx_lines = []
    for m in history[-4:-1]:  # last 2 exchanges, not including current turn
        if m["role"] == "user":
            ctx_lines.append(f"User: {m['content'][:150]}")
        else:
            v = m.get("verdict")
            if v and v.get("reasoning"):
                ctx_lines.append(f"SHIELD: [{v['verdict']}] {v['reasoning'][:200]}")
            else:
                ctx_lines.append(f"SHIELD: {m['content'][:150]}")

    if not ctx_lines:
        return understand_query(question)

    routed = (
        "[Recent conversation]\n"
        + "\n".join(ctx_lines)
        + "\n[Current question] " + question
    )
    return understand_query(routed)


# Main entry point
def analyze(
    question: str,
    history:  list[dict] | None = None,
) -> Optional[Verdict]:
    """
    Single pipeline entry point.

    CLI usage  : analyze(question)
    API usage  : analyze(question, history)

    History flow:
    1. _route()               - intent classification with conversation context
    2. _canned_response()     - immediate return for non-retrieval intents
    3. _build_history_messages() - convert history to LLM message list
    4. retrieval strategy     - vague followup → inherit payload
                                summary request → combine all session payloads
                                normal → use current payload
    5. kg_retrieve / rag_retrieve  - fetch grounding context
    6. _synthesize()          - LLM verdict/explanation with history messages
                                so the model sees and can refer to prior turns
    """
    payload = _route(question, history)
    if not payload:
        return None

    # Non-retrieval intents return immediately
    canned = _canned_response(payload)
    if canned is not None:
        return canned

    # Build history message list (empty list = single-turn, no history effect)
    history_msgs = _build_history_messages(history) if history else []
    memory_suffix = _SYSTEM_MEMORY_SUFFIX if history_msgs else ""

    # Retrieval strategy
    # Summary: pull context from the entire session, not just current payload
    if history and _is_summary_request(question):
        all_payloads = _extract_all_payloads(history)
        if all_payloads:
            rag = _rag_retrieve_combined(all_payloads)
            kg  = kg_retrieve(all_payloads[-1])
            prompt = (f"QUESTION: {question}\n\n"
                      f"PARSED: {payload.model_dump()}\n\n"
                      f"CONTEXT:\n{build_context(kg, rag)}")
            return _synthesize(SYSTEM + memory_suffix, prompt, history_msgs or None)

    # Vague followup: inherit previous payload so retrieval has a real topic
    retrieval_payload = payload
    if history and _is_vague_followup(question):
        inherited = _extract_last_payload(history)
        if inherited:
            retrieval_payload = inherited

    # Synthesis
    if payload.intent == "knowledge":
        rag = rag_knowledge(retrieval_payload)
        prompt = (f"QUESTION: {question}\n\n"
                  f"TOPIC: {payload.topic}\n\n"
                  f"CONTEXT:\n{build_context([], rag)}")
        return _synthesize(SYSTEM_KNOWLEDGE + memory_suffix, prompt, history_msgs or None)

    # scenario
    kg  = kg_retrieve(retrieval_payload)
    rag = rag_retrieve(retrieval_payload)
    prompt = (f"QUESTION: {question}\n\n"
              f"PARSED: {payload.model_dump()}\n\n"
              f"CONTEXT:\n{build_context(kg, rag)}")
    return _synthesize(SYSTEM + memory_suffix, prompt, history_msgs or None)


# Backward-compat alias - api.py calls this signature
def analyze_with_history(question: str, history: list[dict]) -> Optional[Verdict]:
    return analyze(question, history)



def analyze_trace(question: str) -> dict:
    """
    Evaluation harness - returns full trace including retrieved KG/RAG context.
    Called by your eval scripts, not by the live API.
    Does its own retrieval so trace captures intermediate results.
    Uses the same _canned_response() and _synthesize() so outputs are consistent.
    """
    trace = {
        "question": question, "intent": None, "parsed": None,
        "kg": [], "rag": [], "verdict": None, "rules": [],
        "reasoning": "", "confidence": 0,
    }

    payload = understand_query(question)
    if not payload:
        return trace

    trace["intent"] = payload.intent
    trace["parsed"] = payload.model_dump()

    # Canned intents need no retrieval
    result = _canned_response(payload)

    if result is None:
        if payload.intent == "knowledge":
            rag          = rag_knowledge(payload)
            trace["rag"] = rag
            prompt       = (f"QUESTION: {question}\n\n"
                            f"TOPIC: {payload.topic}\n\n"
                            f"CONTEXT:\n{build_context([], rag)[:6000]}")
            result       = _synthesize(SYSTEM_KNOWLEDGE, prompt)
        else:  # scenario
            kg  = kg_retrieve(payload)
            rag = rag_retrieve(payload)
            trace["kg"], trace["rag"] = kg, rag
            prompt = (f"QUESTION: {question}\n\n"
                      f"PARSED: {payload.model_dump()}\n\n"
                      f"CONTEXT:\n{build_context(kg, rag)}")
            result = _synthesize(SYSTEM, prompt)

    if result:
        trace.update(verdict=result.verdict, rules=result.rules,
                     reasoning=result.reasoning, confidence=result.confidence)
    return trace



def _print(v: Verdict) -> None:
    print("=" * 60)
    print(f"VERDICT    : {v.verdict}")
    print(f"RULES      : {', '.join(v.rules) if v.rules else '-'}")
    print(f"CONFIDENCE : {v.confidence}%")
    print(f"REASONING  : {v.reasoning}")
    print("=" * 60)


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else (
        "Can my elderly-care assistant store fall-risk predictions "
        "and share them with caregivers?")
    print(f'Q: "{q}"\n')
    result = analyze(q)
    if result:
        _print(result)
    else:
        print("Could not produce a result.")