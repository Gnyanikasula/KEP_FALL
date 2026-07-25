"""
kep_fall.config — single source of truth for filesystem paths and environment.

Every module imports its paths from here. Nothing anywhere else in the codebase
should contain a string literal that is a path. Two reasons this matters:

  1. Paths were previously written two incompatible ways — Path("data/x.json"),
     which resolves against the *current working directory*, and
     os.path.join(BASE_DIR, ...), which resolves against the *file's own
     location*. Scripts therefore worked only when launched from the repo root,
     and broke silently the moment a file moved. Anchoring everything to ROOT
     removes that class of bug entirely.

  2. It documents the pipeline. Reading this file top to bottom tells you what
     Phase A produces, what Phase B consumes, and so on.

Naming convention: <PHASE>_<ARTEFACT>. Directories are plural, files singular.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --------------------------------------------------------------------------
# Anchor. kep_fall/config.py -> parents[1] is the repository root.
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# --------------------------------------------------------------------------
# Top-level directories
# --------------------------------------------------------------------------
DATA_DIR    = ROOT / "data"
RESULTS_DIR = ROOT / "results"

RAW_DIR      = DATA_DIR / "raw"       # source legislation PDFs (not in git)
CORPUS_DIR   = DATA_DIR / "corpus"    # Phase A output
ONTOLOGY_DIR = DATA_DIR / "ontology"  # Phase B output
GRAPH_DIR    = DATA_DIR / "graph"     # Phase C intermediates
EVAL_DIR     = DATA_DIR / "eval"      # question set + gold standard
CACHE_DIR    = DATA_DIR / "cache"     # resumable checkpoints, LLM caches

EVAL_RESULTS_DIR  = RESULTS_DIR / "evaluation"
AUDIT_RESULTS_DIR = RESULTS_DIR / "context_audit"
BUILD_LOGS_DIR    = RESULTS_DIR / "build_logs"

# --------------------------------------------------------------------------
# Phase A — corpus construction
#   in : five regulation PDFs      out: article/sub-point provision chunks
# --------------------------------------------------------------------------
PDF_GDPR   = RAW_DIR / "GDPR.pdf"
PDF_EU_AI  = RAW_DIR / "EU_AI_ACT.pdf"
PDF_EU_MDR = RAW_DIR / "consolidated_EUMDR.pdf"
PDF_UK_MDR = RAW_DIR / "consolidated_UKMDR.pdf"
PDF_DUAA   = RAW_DIR / "DUAA.pdf"

CORPUS_CHUNKS = CORPUS_DIR / "regulatory_chunks.json"   # 559 chunks

# --------------------------------------------------------------------------
# Phase B — ontology engineering
#   in : corpus + DPV              out: validated OWL ontology (v4)
#   The ontology is versioned across the four construction steps; each version
#   is retained as build evidence, and each passed the HermiT reasoner.
# --------------------------------------------------------------------------
DPV_BASE = Path(os.getenv("DPV_BASE", ROOT / "vendor" / "dpv-2.2.1"))

# The six DPV/OWL modules every Phase B step loads. They must all exist under
# DPV_BASE or owlready2 fails at load. Import this list instead of re-declaring
# it in each step (it was copy-pasted into all four before).
DPV_MODULES = [
    DPV_BASE / "dpv"   / "dpv-owl.rdf",
    DPV_BASE / "pd"    / "pd-owl.rdf",
    DPV_BASE / "risk"  / "risk-owl.rdf",
    DPV_BASE / "ai"    / "ai-owl.rdf",
    DPV_BASE / "legal" / "eu" / "gdpr"  / "eu-gdpr-owl.rdf",
    DPV_BASE / "legal" / "eu" / "aiact" / "eu-aiact-owl.rdf",
]


ONTO_CANDIDATES   = ONTOLOGY_DIR / "candidate_concepts.json"    # step 1
ONTO_ALIGNMENT    = ONTOLOGY_DIR / "alignment_results.json"     # step 1
ONTO_CLASSES      = ONTOLOGY_DIR / "classes_created.json"       # step 1
ONTO_CLASSES_V2   = ONTOLOGY_DIR / "classes_created_v2.json"    # step 2
ONTO_DEDUP_REPORT = ONTOLOGY_DIR / "dedup_report.json"          # step 2
ONTO_LLM_RAW      = ONTOLOGY_DIR / "llm_restrictions_raw.json"  # step 4

ONTOLOGY_V1 = ONTOLOGY_DIR / "dpv-fallrisk-ext-v1.rdf"  # step 1  mine + align
ONTOLOGY_V2 = ONTOLOGY_DIR / "dpv-fallrisk-ext-v2.rdf"  # step 2  re-parent
ONTOLOGY_V3 = ONTOLOGY_DIR / "dpv-fallrisk-ext-v3.rdf"  # step 3  port restrictions
ONTOLOGY_V4 = ONTOLOGY_DIR / "dpv-fallrisk-ext-v4.rdf"  # step 4  LLM restrictions
ONTOLOGY    = ONTOLOGY_V4                               # the one downstream uses

# --------------------------------------------------------------------------
# Phase C — knowledge-graph population
#   in : corpus + ontology         out: typed triples loaded into Neo4j
# --------------------------------------------------------------------------
VOCAB_INDEX          = GRAPH_DIR / "vocab_index.json"              # step 1
CLASS_EMBEDDINGS     = GRAPH_DIR / "class_embeddings.npy"          # step 1 (regenerable)
CLASS_NAME_EMBEDDING = GRAPH_DIR / "class_name_embeddings.npy"     # step 1 (regenerable)
ARTICLES_WITH_CLASSES = GRAPH_DIR / "articles_with_classes.json"   # step 2
TRIPLES_RAW          = GRAPH_DIR / "validated_triples.json"        # step 3
TRIPLES_CLEAN        = GRAPH_DIR / "clean_triples.json"            # step 4 -> Neo4j

EXTRACTION_CHECKPOINT = CACHE_DIR / "triple_extraction_checkpoint.json"

# --------------------------------------------------------------------------
# Phase D — retrieval and synthesis engine
# --------------------------------------------------------------------------
CHROMA_PATH       = str(ROOT / "chroma_db")   # chromadb wants a str, not Path
CHROMA_COLLECTION = "regulations"
SUMMARY_CACHE     = CACHE_DIR / "article_summaries.json"
WEB_DIR           = ROOT / "kep_fall" / "phase_d_engine" / "web"
HISTORY_DB        = Path(os.getenv("HISTORY_DB_PATH", CACHE_DIR / "kep_fall_history.db"))

# --------------------------------------------------------------------------
# Phase E — evaluation
# --------------------------------------------------------------------------
COMPETENCY_QUESTIONS = EVAL_DIR / "competency_questions.json"   # 65 questions
GOLD_STANDARD        = EVAL_DIR / "gold_standard.json"          # 55 annotations

ABLATION_RESULTS    = EVAL_RESULTS_DIR / "ablation_results.json"
ABLATION_CHECKPOINT = EVAL_RESULTS_DIR / "ablation_checkpoint.json"

# --------------------------------------------------------------------------
# Models and credentials
# --------------------------------------------------------------------------
LLM_MODEL   = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def ensure_dirs() -> None:
    """Create every output directory. Call once at the top of any build script."""
    for d in (RAW_DIR, CORPUS_DIR, ONTOLOGY_DIR, GRAPH_DIR, EVAL_DIR, CACHE_DIR,
              EVAL_RESULTS_DIR, AUDIT_RESULTS_DIR, BUILD_LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def require_env(*names: str) -> None:
    """Fail loudly and early if a credential is missing, rather than at call time."""
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise RuntimeError(
            f"Missing environment variable(s): {', '.join(missing)}. "
            f"Copy .env.example to .env and fill them in."
        )