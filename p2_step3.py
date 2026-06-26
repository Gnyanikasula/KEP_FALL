"""
Step 3 — Schema-Constrained Triple Extraction (LLM-as-Typer)
=============================================================
Correct architecture:
  - Embeddings RETRIEVE candidate classes (top-K per article)
  - LLM SELECTS the exact class from candidates, or marks concept as NEW
  - No blind nearest-neighbor mapping, no forced bad matches

Each triple node is either:
  typed=true   → matched a real ontology class (has URI)
  typed=false  → new organic node (no URI, source="extracted")

Resumable via checkpoint. Long articles handled by sliding window.
"""

import json
import logging
import os
import re
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field, field_validator
from sentence_transformers import SentenceTransformer

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

ARTICLES_PATH   = Path("data/articles_with_classes.json")
VOCAB_PATH      = Path("data/vocab_index.json")
EMBED_NAME_PATH = Path("data/class_name_embeddings.npy")
OUTPUT_PATH     = Path("data/validated_triples.json")
CHECKPOINT_PATH = Path("checkpoints/step3_checkpoint.json")

WINDOW_WORDS    = 2000
OVERLAP_WORDS   = 150
MIN_CONFIDENCE  = 0.7
MAX_TRIPLES     = 12
CANDIDATE_K     = 30          # candidate classes shown to LLM per article

# Base DPV classes — always injected into every candidate list so common
# legal concepts (Processing, DataSubject, etc.) always have a clean target.
ALWAYS_INCLUDE = {
    "Processing", "PersonalData", "DataSubject", "DataController",
    "LegalBasis", "Consent", "Purpose", "Right", "Obligation", "Risk",
    "TechnicalMeasure", "OrganisationalMeasure", "Notice", "Entity",
}

client   = Groq(api_key=os.getenv("GROQ_API_KEY"))
embedder = SentenceTransformer("all-MiniLM-L6-v2")


# ─────────────────────────────────────────────────────────────────────────────
# Triple schema
# ─────────────────────────────────────────────────────────────────────────────

class RawTriple(BaseModel):
    subject    : str
    subject_type: str = "NEW"          # exact candidate name, or "NEW"
    predicate  : str
    object     : str
    object_type : str = "NEW"          # exact candidate name, or "NEW"
    confidence : float = Field(ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except Exception:
            return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Candidate retrieval — embeddings choose what LLM sees
# ─────────────────────────────────────────────────────────────────────────────

def build_candidates(article: dict, vocab_classes: list[dict]) -> list[dict]:
    """
    Candidate classes the LLM picks from = article top-K + always-include base classes.
    """
    by_name = {c["name"]: c for c in vocab_classes}

    candidates = {}
    for c in article["top_classes"][:CANDIDATE_K]:
        if c["name"] in by_name:
            candidates[c["name"]] = by_name[c["name"]]

    for name in ALWAYS_INCLUDE:
        if name in by_name:
            candidates[name] = by_name[name]

    return list(candidates.values())


# ─────────────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a legal knowledge extractor for data protection and AI regulation.

You extract RDF triples (subject — predicate — object) from regulatory text.

For each triple you must classify the subject and object against an ontology:
- If the concept matches one of the CANDIDATE CLASSES, set its type to that EXACT class name.
- If no candidate class fits, set its type to "NEW" and give a short clean concept name.

Rules:
- predicate MUST be copied exactly from the ALLOWED PREDICATES list.
- subject_type and object_type MUST be either an exact candidate class name or "NEW".
- subject and object are short human-readable concept names (2-4 words).
- confidence is your certainty in the triple (0.0-1.0).
- Output ONLY a valid JSON array. No prose, no markdown.

Format:
[{"subject":"...","subject_type":"ExactClassName or NEW","predicate":"exactPredicate","object":"...","object_type":"ExactClassName or NEW","confidence":0.9}]"""


def build_user_prompt(article: dict, text_window: str, properties: list[dict],
                      candidates: list[dict], window_num: int, total_windows: int) -> str:
    pred_lines = "\n".join(f"- {p['label']}" for p in properties)
    cand_lines = "\n".join(f"- {c['name']}" for c in candidates)
    window_note = f" (part {window_num} of {total_windows})" if total_windows > 1 else ""

    return f"""Regulation: {article['regulation']}
Article: {article['article_num']} — {article['article_title']}{window_note}

TEXT:
{text_window}

ALLOWED PREDICATES (copy exactly):
{pred_lines}

CANDIDATE CLASSES (use exact name, or "NEW" if none fit):
{cand_lines}

Extract up to {MAX_TRIPLES} triples. Return JSON array only."""


# ─────────────────────────────────────────────────────────────────────────────
# LLM call
# ─────────────────────────────────────────────────────────────────────────────

def call_llm(user_prompt: str, retries: int = 2) -> str | None:
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1500,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.warning(f"  LLM call failed (attempt {attempt + 1}): {e}")
            time.sleep(2)
    return None


def parse_response(raw: str) -> list[RawTriple]:
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip()

    try:
        items = json.loads(clean)
    except json.JSONDecodeError as e:
        log.warning(f"  JSON parse failed: {e}")
        return []

    if not isinstance(items, list):
        return []

    out = []
    for item in items:
        try:
            out.append(RawTriple(**item))
        except Exception:
            continue
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Validation — LLM's type choice is trusted, only verified against candidates
# ─────────────────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    return s.lower().replace(" ", "").replace("_", "").replace("-", "")


def slugify(concept: str) -> str:
    """Turn 'data subject' into 'DataSubject' for new-node identity."""
    parts = re.split(r"[\s_\-]+", concept.strip())
    return "".join(p.capitalize() for p in parts if p)


def resolve_node(concept: str, node_type: str,
                 cand_by_norm: dict, vocab_by_norm: dict) -> dict:
    """
    Resolve a node to either a typed ontology class or a new organic node.
    LLM's type selection is the primary signal; we verify it's a real class.
    """
    if node_type and node_type.upper() != "NEW":
        key = normalize(node_type)
        # verify the type is a real class (prefer candidate, fall back to full vocab)
        cls = cand_by_norm.get(key) or vocab_by_norm.get(key)
        if cls:
            return {
                "label": cls["name"],
                "uri"  : cls["uri"],
                "typed": True,
            }

    # New organic node — no ontology match
    return {
        "label": slugify(concept),
        "uri"  : None,
        "typed": False,
    }


def validate_and_type(raw_triples: list[RawTriple], article: dict,
                      properties: list[dict], candidates: list[dict],
                      vocab_classes: list[dict]) -> list[dict]:
    allowed_props = {normalize(p["label"]): p for p in properties}
    cand_by_norm  = {normalize(c["name"]): c for c in candidates}
    vocab_by_norm = {normalize(c["name"]): c for c in vocab_classes}

    valid = []
    for t in raw_triples:
        if t.confidence < MIN_CONFIDENCE:
            continue

        pred_key = normalize(t.predicate)
        if pred_key not in allowed_props:
            log.warning(f"  Rejected predicate: '{t.predicate}'")
            continue

        subj = resolve_node(t.subject, t.subject_type, cand_by_norm, vocab_by_norm)
        obj  = resolve_node(t.object,  t.object_type,  cand_by_norm, vocab_by_norm)

        s_mark = "●" if subj["typed"] else "○"
        o_mark = "●" if obj["typed"]  else "○"
        log.info(f"  {s_mark} {subj['label']} --{t.predicate}--> {o_mark} {obj['label']}  ({t.confidence})")

        valid.append({
            "subject_label"  : subj["label"],
            "subject_uri"    : subj["uri"],
            "subject_typed"  : subj["typed"],
            "predicate_label": allowed_props[pred_key]["label"],
            "predicate_uri"  : allowed_props[pred_key]["uri"],
            "object_label"   : obj["label"],
            "object_uri"     : obj["uri"],
            "object_typed"   : obj["typed"],
            "confidence"     : t.confidence,
            "llm_subject"    : t.subject,
            "llm_object"     : t.object,
            "provenance"     : {
                "regulation" : article["regulation"],
                "article_id" : article["article_id"],
                "article_num": article["article_num"],
                "chunk_ids"  : article["chunk_ids"],
            },
        })
    return valid


def deduplicate(triples: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for t in triples:
        key = (t["subject_label"].lower(), t["predicate_label"].lower(), t["object_label"].lower())
        if key not in seen or t["confidence"] > seen[key]["confidence"]:
            seen[key] = t
    return list(seen.values())


# ─────────────────────────────────────────────────────────────────────────────
# Article processing — sliding window for long articles
# ─────────────────────────────────────────────────────────────────────────────

def split_text(text: str) -> list[str]:
    words = text.split()
    if len(words) <= WINDOW_WORDS:
        return [text]
    windows, start = [], 0
    while start < len(words):
        end = min(start + WINDOW_WORDS, len(words))
        windows.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - OVERLAP_WORDS
    return windows


def process_article(article: dict, properties: list[dict], vocab_classes: list[dict]) -> list[dict]:
    candidates = build_candidates(article, vocab_classes)
    windows    = split_text(article["merged_text"])
    total      = len(windows)
    if total > 1:
        log.info(f"  Long article split into {total} windows")

    all_raw = []
    for i, window in enumerate(windows, 1):
        prompt = build_user_prompt(article, window, properties, candidates, i, total)
        raw    = call_llm(prompt)
        if raw is None:
            log.warning(f"  Window {i}/{total} failed")
            continue
        all_raw.extend(parse_response(raw))

    validated    = validate_and_type(all_raw, article, properties, candidates, vocab_classes)
    deduped      = deduplicate(validated)

    typed   = sum(1 for t in deduped if t["subject_typed"] and t["object_typed"])
    partial = len(deduped) - typed
    log.info(f"  Valid: {len(deduped)}  (fully-typed: {typed}, has-new-node: {partial})")
    return deduped


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint / IO
# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    articles = load_json(ARTICLES_PATH, [])
    vocab    = load_json(VOCAB_PATH, {})

    properties    = vocab["properties"]
    vocab_classes = vocab["classes"]

    checkpoint  = load_json(CHECKPOINT_PATH, {})
    all_triples = load_json(OUTPUT_PATH, [])
    done_ids    = {k for k, v in checkpoint.items() if v["status"] == "done"}

    if done_ids:
        log.info(f"Resuming — {len(done_ids)} done, {len(articles) - len(done_ids)} remaining")

    for article in articles:
        aid = article["article_id"]
        if aid in done_ids:
            continue

        log.info(f"Processing: {aid}  ({len(article['merged_text'].split())} words)")
        try:
            triples = process_article(article, properties, vocab_classes)
        except Exception as e:
            log.error(f"  Error: {e}")
            checkpoint[aid] = {"status": "failed", "triples": 0}
            save_json(CHECKPOINT_PATH, checkpoint)
            continue

        all_triples.extend(triples)
        checkpoint[aid] = {"status": "done", "triples": len(triples)}
        save_json(CHECKPOINT_PATH, checkpoint)
        save_json(OUTPUT_PATH, all_triples)

    done   = sum(1 for v in checkpoint.values() if v["status"] == "done")
    fails  = sum(1 for v in checkpoint.values() if v["status"] == "failed")
    typed  = sum(1 for t in all_triples if t["subject_typed"] and t["object_typed"])
    new_n  = sum(1 for t in all_triples if not (t["subject_typed"] and t["object_typed"]))

    print(f"\nArticles processed : {done}")
    print(f"Articles failed    : {fails}")
    print(f"Total triples      : {len(all_triples)}")
    print(f"  fully-typed      : {typed}")
    print(f"  with new node    : {new_n}")
    print(f"Output             : {OUTPUT_PATH}")
    print("Next → step4_validation.py")


if __name__ == "__main__":
    main()