---
title: KEP FALL
emoji: 🛡️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---
# KEP_FALL — Structured Healthcare Intelligence for Ethical and Legal Decisions

> A Knowledge-Graph-augmented RAG system for healthcare AI compliance, covering GDPR, EU AI Act, EU MDR 2017/745, UK MDR 2002, and the Data (Use and Access) Act 2025 (DUAA 2025).

---

## What is KEP_FALL?

KEP_FALL answers regulatory compliance questions for healthcare AI and medical device products. It combines a **semantic knowledge graph** (Neo4j AuraDB) built from five major regulations with a **vector retrieval layer** (ChromaDB + nomic-embed-text-v1.5) and an **LLM synthesis layer** (Llama 4 Scout via Groq) to produce answers that cite specific articles, identify applicable obligations, and distinguish between EU and UK jurisdictions.

It is designed for founders, engineers, researchers, and investors who need to know whether their product is compliant — not a generic chatbot, but a pipeline that reasons over structured regulatory knowledge.

---

## Architecture Overview

```
User Question
      │
      ▼
┌─────────────────┐
│  Stage 5: Query  │   route.py
│  Understanding   │   understand_query() → QueryPayload
│  & Routing       │   Intent: scenario | knowledge | ...
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│              Stage 6: Retrieval + Synthesis          │   verdict.py
│                                                      │
│   Knowledge Graph (Neo4j AuraDB)                     │
│     kg_retrieve() → Cypher graph traversal           │
│     Typed concept nodes + REL edges                  │
│     Provenance: regulation, article_id, chunk_ids    │
│                                                      │
│   Vector Store (ChromaDB)                            │
│     rag_retrieve() / rag_knowledge()                 │
│     nomic-embed-text-v1.5 embeddings                 │
│     Chunked article text with metadata               │
│                                                      │
│   build_context(kg, rag) → LLM prompt               │
│   _synthesize() → Verdict (structured JSON)          │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  FastAPI / REST  │   api.py
│  POST /query     │   uvicorn :7860
│  SQLite history  │   data/shield_history.db
└─────────────────┘
```

**Three retrieval modes (used in evaluation and available via API):**

| Mode | What it uses | Notes |
|------|-------------|-------|
| `hybrid` | KG + RAG together | Production — best F1 overall |
| `kg_only` | Knowledge Graph traversal only | Highest citation precision |
| `rag_only` | Vector search only | Baseline comparison |

---

## Regulations Covered

| Regulation | Scope | Jurisdiction |
|-----------|-------|-------------|
| GDPR (2016/679) | Data protection and processing | EU |
| EU AI Act (2024/1689) | AI system risk classification and obligations | EU |
| EU MDR 2017/745 | Medical device conformity assessment | EU |
| UK MDR 2002 (SI 2002/618) | UK medical device regulations post-Brexit | UK |
| DUAA 2025 | Automated significant decisions, data intermediaries | UK |

---

## Pipeline Stages

```
Phase 1 — Ontology Design
  └── OWL ontology (HermiT reasoner validated ✓)

Phase 2 — Regulation Ingestion
  ├── p2_step1: PDF → raw text chunks
  ├── p2_step2: Chunk cleaning and deduplication
  ├── p2_step3: Triple extraction (LLM → subject/predicate/object)
  ├── p2_step4: Triple validation and confidence scoring
  └── p2_step5_aura_graph.py: Load clean_triples.json → Neo4j AuraDB

Phase 3 — Vector Index
  └── rag.py: Embed article chunks → ChromaDB

Phase 4 — Evaluation
  ├── eval_questions_full.json: 60 competency questions (6 groups, A–F)
  ├── gold_standard_full.json: Deontic annotations per article chunk
  └── eval_p4.py: Ablation harness (hybrid / kg_only / rag_only)

Phase 5 — API + Deployment
  ├── api.py: FastAPI application
  └── Dockerfile: Container image for Hugging Face Spaces
```

---

## Evaluation Results (Phase 4)

60 competency questions across 6 regulatory groups (A–F), scored on citation F1, concept coverage, KG hit rate, and deontic alignment.

### Overall Performance

| Mode | Citation F1 | Precision | Recall | KG Hit Rate |
|------|------------|-----------|--------|-------------|
| **hybrid** | **0.660** | 0.606 | 0.817 | **1.000** |
| kg_only | 0.588 | 0.524 | 0.754 | 1.000 |
| rag_only | 0.512 | 0.458 | 0.665 | 0.000 |

Hybrid outperforms pure vector search by **+14.8pp F1**, validating the research contribution: KG-augmented retrieval produces more precise, citable answers than semantic search alone.

### Per-Group (hybrid mode)

| Group | Regulation | n | Citation F1 |
|-------|-----------|---|-------------|
| A | GDPR | 15 | 0.760 |
| B | EU AI Act | 18 | 0.669 |
| C | Cross-regulation | 5 | 0.291 ¹ |
| D | EU MDR 2017/745 | 10 | 0.667 |
| E | UK MDR 2002 | 8 | 0.682 |
| F | DUAA 2025 | 4 | 0.642 |

> ¹ Group C, n=5 — indicative only.

---

## Project Structure

```
├── api.py                     # FastAPI app — POST /query
├── route.py                   # Query understanding and intent classification
├── verdict.py                 # KG + RAG retrieval and LLM synthesis
├── rag.py                     # ChromaDB index builder and retrieval
├── p2_step5_aura_graph.py     # Neo4j AuraDB population
│
├── eval_p4.py                 # Phase 4 evaluation harness
├── eval_questions_full.json   # 60 competency questions
├── gold_standard_full.json    # Deontic annotations
│
├── data/                      # clean_triples.json (gitignored)
├── chroma_db/                 # ChromaDB store (not in repo — build locally)
│
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Environment Variables

```env
# Groq — LLM inference (Llama 4 Scout)
GROQ_API_KEY=your_groq_api_key

# Neo4j AuraDB — knowledge graph
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j

# Optional
HISTORY_DB_PATH=data/shield_history.db
```

---

## Local Setup

### 1. Clone and install

```bash
git clone https://github.com/Gnyanikasula/KEP_FALL.git
cd KEP_FALL
git checkout gny

pip install -r requirements.txt
cp .env.example .env
# Fill in your keys
```

### 2. Build the ChromaDB vector index

**Must be done before running the API or building the Docker image.**

```bash
python rag.py
```

This embeds all article chunks and writes the `chroma_db/` directory locally.

### 3. Run the API

```bash
uvicorn api:app --host 0.0.0.0 --port 7860 --reload
```

### 4. Example request

```bash
curl -X POST http://localhost:7860/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Can my elderly-care assistant store fall-risk predictions and share them with caregivers?"}'
```

---

## Docker

```bash
# Step 1 — build ChromaDB first
python rag.py

# Step 2 — build image
docker build -t shield .

# Step 3 — run
docker run -p 7860:7860 \
  -e GROQ_API_KEY=your_key \
  -e NEO4J_URI=your_uri \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=your_password \
  shield
```

---

## Running the Evaluation

```bash
# Full run — all 60 questions, all 3 modes
python eval_p4.py

# Resume interrupted run
python eval_p4.py

# Reset and re-run from scratch
python eval_p4.py --reset

# Single group only
python eval_p4.py --group A
```

Results written to `Results/`:
- `eval_phase4_checkpoint.json` — per-question results, saved after every question
- `eval_phase4_results.json` — final aggregate + per-question
- `eval_phase4_summary.csv` — flat table

---

## License

Academic project. All rights reserved. Not licensed for commercial use.