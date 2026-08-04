---
title: KEP FALL
emoji: 🛡️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# KEP_FALL

**A Knowledge-Graph-Augmented Retrieval-Augmented Generation System for
Healthcare-AI Regulatory Compliance**

KEP_FALL answers regulatory compliance questions about healthcare AI and
medical devices, and grounds every answer in a named provision. It combines
an ontology-typed knowledge graph over five regulations with a dense vector
store, and evaluates the combination against each component in isolation.

**Live demo:** https://huggingface.co/spaces/gnyani007/KEP_FALL. It runs the
Phase D engine only. No Neo4j credentials are needed to try it, see
[Retrieval modes](#retrieval-modes) below for what that means for the
answers you'll get.

**Research question.** Does augmenting retrieval with a typed,
ontology-grounded knowledge graph improve the accuracy and *groundedness* of
regulatory citations over dense retrieval alone?

**Regulations in scope.** GDPR (2016/679), EU AI Act (2024/1689),
EU MDR 2017/745, UK MDR 2002 (SI 2002/618), DUAA 2025.

---

## How the pieces fit together

The system is built in five phases, each consuming the previous phase's
output. The package layout mirrors these phases exactly. A directory under
`kep_fall/` corresponds to one section of the dissertation, so if you're
looking for "where does X happen," the phase name tells you the folder.

| Phase | Package | Input | Output | Scale |
|---|---|---|---|---|
| **A** Corpus construction | `phase_a_corpus/` | 5 regulation PDFs | provision chunks | 559 chunks |
| **B** Ontology engineering | `phase_b_ontology/` | corpus + DPV | validated OWL ontology | 624 new classes, 641 total |
| **C** KG population | `phase_c_graph/` | corpus + ontology | Neo4j property graph | 618 triples, 545 nodes, 55 articles |
| **D** Retrieval & synthesis | `phase_d_engine/` | user question | cited answer | 3 retrieval modes |
| **E** Evaluation | `phase_e_eval/` | question set | metrics + bootstrap CIs | 65 questions, 3 arms |

**Phases A to C are an offline build.** They run once (or once per
regulation update) and their output is checked-in data, so you do not need to
re-run them to use the system. **Phase D is the live runtime.** This is the
FastAPI service you actually start. **Phase E is how the dissertation's
numbers were produced.** It's a batch evaluation harness, not something a
user runs.

```
                                    ┌──────────────────────────────┐
  A  PDFs ──► provision chunks ─────┤                              │
                    │               │                              │
  B  chunks + DPV ──► OWL ontology  │  D  question                 │
                    │        │      │       │                      │
  C  chunks + ontology ──► Neo4j ───┤       ├─► router             │
                    │               │       ├─► graph retrieval ───┼─► context
  D  chunks ──► ChromaDB ───────────┤       ├─► vector retrieval ──┤    │
                                    │       │                      │    ▼
                                    │       └──────────────────────┼─► LLM ─► cited verdict
                                    └──────────────────────────────┘
                                                  │
  E  65 competency questions ──► ablation ────────┘──► faithful F1, CIs
```

---

## Repository layout: what every file is for

```
kep_fall/                          the installable package; PYTHONPATH root is the repo root
├── config.py                      # single source of truth for every path + env var
├── citation.py                    # canonical article-id format shared by Chroma, Neo4j and the API
│
├── phase_a_corpus/                 PHASE A: turns raw PDFs into structured chunks
│   ├── parse_eu_gdpr_aiact.py     # GDPR + EU AI Act -> data/corpus/regulatory_chunks.json
│   └── parse_uk_mdr_duaa.py       # UK MDR + EU MDR + DUAA -> same file, appended
│
├── phase_b_ontology/                PHASE B: extends the DPV ontology with fall-risk concepts
│   ├── step1_mine_and_align.py    # candidate concepts, TF-IDF + LLM alignment -> ontology v1
│   ├── step2_reparent_classes.py  # re-parent orphan classes, dedup -> v2
│   ├── step3_port_restrictions.py # port v1 restrictions forward, deterministic -> v3
│   └── step4_llm_restrictions.py  # LLM-proposed OWL restrictions, HermiT-validated -> v4 (final)
│
├── phase_c_graph/                   PHASE C: extracts triples and loads them into Neo4j
│   ├── step1_build_vocab_index.py # embeds every ontology class for similarity search
│   ├── step2_candidate_classes.py # top-K candidate classes per article
│   ├── step3_extract_triples.py   # schema-constrained LLM extraction ("LLM-as-typer")
│   ├── step4_reconcile_triples.py # dedup, sanitise, validate against the ontology
│   ├── step5_load_graph.py        # writes nodes/edges to Neo4j, tags deontic modality + canonical id
│   └── validate_graph.py          # structural / coverage / provenance sanity queries
│
├── phase_d_engine/                  PHASE D: this is what you actually run day-to-day
│   ├── router.py                  # question text -> QueryPayload (intent classification + concept extraction)
│   ├── vector_store.py            # builds/queries the Chroma dense index
│   ├── graph_store.py             # Neo4j driver wrapper, timeout-guarded (see config.py NEO4J_TIMEOUT)
│   ├── engine.py                  # orchestrates retrieval (graph + vector), assembles context, calls the LLM
│   ├── history.py                 # SQLite-backed conversation/session store
│   ├── eval_data.py               # serves the Phase E results to the /evaluation endpoint
│   ├── api.py                     # FastAPI app. This is the module uvicorn points at
│   └── web/                       # static front-end (index.html / app.js / style.css) served at "/"
│
└── phase_e_eval/                    PHASE E: offline, only for reproducing the dissertation numbers
    ├── harness.py                 # runs the 65-question ablation across hybrid/kg_only/rag_only, resumable
    ├── report.py                  # turns the checkpoint into the CSVs in results/evaluation/
    └── context_audit/             # diagnostic scripts that found the context-truncation defect

data/
├── raw/          # source PDFs. NOT in git, you must supply these yourself (see below)
├── corpus/       # Phase A output
├── ontology/     # Phase B output, versions v1 to v4
├── graph/        # Phase C intermediates
├── eval/         # competency questions + gold standard used by Phase E
└── cache/        # resumable checkpoints, LLM response caches, the SQLite history DB at runtime

chroma_db/        # the pre-built dense vector index. Phase D reads this directly, must exist before `make api`
results/
├── evaluation/   # ablation results + CSVs. This is the dissertation's evidence
├── context_audit/
└── performance/  # latency_bench.py / concurrency_bench.py output
scripts/          # verify_setup.py (preflight), trace_kg.py (debug a single query), benchmarks
tests/            # pytest, currently just graph-parity checks
docs/             # gold_standard_audit.md documents 7 corrections made to the gold standard
```

### Two things worth flagging before you touch anything

1. **Root-level stragglers.** `config.py`, `test_citation.py` and
   `restructure.sh` at the repo root look like leftovers from the
   `SHIELD → KEP_FALL` package rename. They duplicate `kep_fall/config.py`
   and `tests/test_citation.py`. `trace_final2.txt` looks like a stray debug
   log. None of these are imported by the running app (everything imports
   `from kep_fall import config`, not the root one), but they're dead weight
   and worth deleting once you've confirmed nothing references them.
   `grep -rn "^import config\|^from config"` should come back empty first.
2. **No `.env.example` in this drop.** `config.py` reads `GROQ_API_KEY`,
   `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`,
   `NEO4J_TIMEOUT`, `HISTORY_DB_PATH`, `LLM_MODEL`, `EMBED_MODEL` and
   `DPV_BASE` via `os.getenv`, all with safe fallbacks except the Groq key
   and Neo4j password. Create a `.env` by hand with at least
   `GROQ_API_KEY=...`, see [Setup](#setup) below.

---

## Setup

```bash
git clone <repo> && cd KEP_FALL
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` in the repo root:

```bash
GROQ_API_KEY=your_groq_key_here

# Optional. Only needed for hybrid/kg_only retrieval. Leave unset and the
# engine still runs in a degraded mode, see "Retrieval modes" below.
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
NEO4J_DATABASE=neo4j
```

The Chroma vector index (`chroma_db/`) ships pre-built in this repo, so you
do **not** need to rebuild it or run Phases A to C to get the API running. If
`chroma_db/` is ever missing or you change the corpus, rebuild it with:

```bash
python -m kep_fall.phase_d_engine.vector_store
```

---

## Running it locally

This is the command you had, plus the two flags that make it behave the same
way `make api` does:

```bash
uvicorn kep_fall.phase_d_engine.api:app --host 0.0.0.0 --port 7860 --reload
```

Your original (`uvicorn kep_fall.phase_d_engine.api:app --port 7860`) works
fine too. `--host` just controls which network interfaces it binds to
(`0.0.0.0` means "reachable from other devices on your network," `127.0.0.1`,
the default, means "localhost only"), and `--reload` restarts the server on
code changes, which you want during development and don't want in
production. It's `--port 7860` either way because that's what
`HISTORY_DB_PATH`, the Dockerfile's `EXPOSE`, and the Hugging Face Space's
`app_port` in this file's front-matter all agree on. Changing it in one
place without the others will just make things quietly stop connecting.

Or, more simply, use the Makefile target that wraps the exact same command:

```bash
make api        # -> http://localhost:7860
```

Once it's up:
- API: `http://localhost:7860` (interactive docs at `/docs`)
- Web UI: served at `/` from `kep_fall/phase_d_engine/web/`
- Health check: `GET /health` and `GET /health/deep` (the latter actually
  pings Neo4j and Chroma, not just "is the process alive")

Before your first run, it's worth running the preflight check. It verifies
your credentials, the Neo4j schema, and the Chroma index all exist and agree
with each other, and fails with a clear message instead of a stack trace deep
in a request handler:

```bash
make verify      # python scripts/verify_setup.py
```

### All Makefile targets

```bash
make help        # prints this same list with descriptions
make install      # pip install -r requirements-dev.txt
make verify       # preflight: credentials, Neo4j schema, Chroma index

# offline build. Run once, only if reproducing from source (see below)
make corpus       # Phase A
make ontology     # Phase B, LLM calls, slow
make graph        # Phase C, LLM calls, slow, checkpointed/resumable

# runtime
make index        # Phase D. (Re)build the Chroma vector index
make api           # serve the API + web UI on :7860. What you want day-to-day

# evaluation
make eval         # Phase E, full 65-question ablation, resumable
make report       # regenerate CSVs in results/evaluation/ from the checkpoint

make test          # pytest -q
make clean         # remove __pycache__ / .pytest_cache, leaves data/ and results/ alone
```

### Rebuilding from source (only if you're reproducing the whole pipeline)

You only need this if you're regenerating the ontology or the graph, not to
run the app day-to-day. Requires the five source PDFs in `data/raw/` (not in
git, see `docs/DATA_SOURCES.md`) and the DPV 2.2.1 release under `vendor/`.

```bash
make corpus       # Phase A. Fast, no LLM calls
make ontology     # Phase B. LLM calls, slow
make graph        # Phase C. LLM calls, slow, checkpointed (safe to interrupt/resume)
make index        # Phase D. Rebuild the vector index from the new corpus
```

### Running the evaluation

```bash
make eval         # full ablation; interrupt and re-run to resume from checkpoint
make report        # regenerate CSVs from the checkpoint
```

Two extra flags on the harness directly:

```bash
python -m kep_fall.phase_e_eval.harness --reset      # start over instead of resuming
python -m kep_fall.phase_e_eval.harness --group A     # run only question group A
```

---

## Running with Docker

The Dockerfile builds the Phase D runtime only (it does not run Phases A to
C, so the Chroma index must already exist before you build the image).

```bash
python -m kep_fall.phase_d_engine.vector_store   # only if chroma_db/ doesn't already exist
python scripts/verify_setup.py                    # confirm everything is healthy
docker build -t kep-fall .
docker run -p 7860:7860 --env-file .env kep-fall
```

This is also exactly what the Hugging Face Space at
https://huggingface.co/spaces/gnyani007/KEP_FALL runs. It builds this same
Dockerfile. Its `.env` there is set via the Space's *Settings > Repository
secrets*, not a committed file.

---

## Retrieval modes

| Mode | Uses | Role |
|---|---|---|
| `hybrid` | graph + vector store | production; the full system |
| `kg_only` | graph traversal only | isolates the graph's standalone value |
| `rag_only` | dense retrieval only | the baseline being tested against |

The evaluation harness additionally supports `kg_typed_only` and
`kg_untyped_only` for the ontology ablation specifically.

**If Neo4j isn't configured** (no `NEO4J_URI`/`NEO4J_PASSWORD`, or the
instance is paused, which matters on the Aura free tier), graph retrieval
fails fast within `NEO4J_TIMEOUT` seconds (default 3s, see `config.py`) and
the engine falls back to `rag_only` behaviour rather than hanging. The
Hugging Face Space demo runs this way, which is why it's flagged above.

---

## Debugging a single query

`scripts/trace_kg.py` walks one question through every stage of graph
retrieval: the router's payload, keyword derivation, the exact Cypher query
with bound parameters, raw hits, ranked hits with scores, and the final
assembled context block. It never calls the LLM, so it's free and fast to
run, and it's how the retrieval defects described in the evaluation report
were originally found.

```bash
python scripts/trace_kg.py "What lawful bases justify processing health data?"
```

---

## Results (headline numbers)

65 competency questions (61 knowledge, 4 scenario) across seven groups,
evaluated as a three-arm ablation. Full outputs in `results/evaluation/`.

| Arm | Faithful F1 | Naive F1 | Hallucination | Answerability | Concept cov. | Deontic align. |
|---|---|---|---|---|---|---|
| **hybrid** | **0.845** | 0.829 | **0.027** | 0.869 | 0.588 | **0.496** |
| kg_only | 0.748 | 0.770 | 0.074 | 0.869 | 0.459 | 0.447 |
| rag_only | 0.753 | 0.754 | 0.030 | n/a | **0.626** | 0.289 |

"Faithful F1" only credits a citation if the system actually retrieved that
article. A citation the model recalled from its own parameters, without it
appearing anywhere in retrieved context, earns nothing. That gap between
faithful and naive F1 is what quantifies parametric leakage. Full statistical
tests and per-group breakdowns are in the results directory and in
`docs/gold_standard_audit.md`, which documents the seven corrections made to
the gold standard before these numbers were produced. Treat groups with
n ≤ 5 (flagged `warn_small_n` in `summary_by_group.csv`) as indicative, not
conclusive.

---

## License

Academic project submitted for assessment. All rights reserved; not licensed
for commercial use. Source legislation is reproduced under the terms of the
respective publishers.