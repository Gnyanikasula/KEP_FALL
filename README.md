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

**A Knowledge-Graph-Augmented Retrieval-Augmented Generation System for Healthcare-AI Regulatory Compliance**

KEP_FALL answers regulatory compliance questions about healthcare AI and medical
devices, and grounds every answer in a named provision. It combines an
ontology-typed knowledge graph over five regulations with a dense vector store,
and evaluates the combination against each component in isolation.

**Research question.** Does augmenting retrieval with a typed,
ontology-grounded knowledge graph improve the accuracy and *groundedness* of
regulatory citations over dense retrieval alone?

**Regulations in scope.** GDPR (2016/679) · EU AI Act (2024/1689) ·
EU MDR 2017/745 · UK MDR 2002 (SI 2002/618) · DUAA 2025

---

## Pipeline

The system is built in five phases, each consuming the previous phase's output.
Package layout mirrors these phases exactly, so a directory in `kep_fall/`
corresponds to a section of the dissertation.

| Phase | Package | Input | Output | Scale |
|---|---|---|---|---|
| **A** Corpus construction | `phase_a_corpus/` | 5 regulation PDFs | provision chunks | 559 chunks |
| **B** Ontology engineering | `phase_b_ontology/` | corpus + DPV | validated OWL ontology | 624 new classes, 641 total |
| **C** KG population | `phase_c_graph/` | corpus + ontology | Neo4j property graph | 618 triples, 545 nodes, 55 articles |
| **D** Retrieval & synthesis | `phase_d_engine/` | user question | cited answer | 3 retrieval modes |
| **E** Evaluation | `phase_e_eval/` | question set | metrics + bootstrap CIs | 65 questions, 3 arms |

Phases A–C are an offline build, run once and re-run only when a regulation
changes. Phase D is the runtime system. Phase E measures it.

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

## Results

65 competency questions (61 knowledge, 4 scenario) across seven groups,
evaluated as a three-arm ablation. Full outputs in `results/evaluation/`.

**Headline metric — faithful F1.** Citation F1 against the gold articles, but a
cited article counts *only if the system actually retrieved it*. An article
named in the answer that appears nowhere in the retrieved context was recalled
from the model's parameters, not retrieved, and earns no credit. Naive F1
(crediting any correct citation) is reported alongside; the gap between the two
quantifies parametric leakage.

| Arm | Faithful F1 | Naive F1 | Hallucination | Answerability | Concept cov. | Deontic align. |
|---|---|---|---|---|---|---|
| **hybrid** | **0.845** | 0.829 | **0.027** | 0.869 | 0.588 | **0.496** |
| kg_only | 0.748 | 0.770 | 0.074 | 0.869 | 0.459 | 0.447 |
| rag_only | 0.753 | 0.754 | 0.030 | n/a | **0.626** | 0.289 |

Paired bootstrap, 5,000 resamples, seeded:

| Comparison | Δ | 95% CI | p | Significant |
|---|---|---|---|---|
| hybrid − rag_only, faithful F1 | +0.092 | [0.021, 0.168] | 0.009 | **yes** |
| hybrid − rag_only, deontic align. | +0.207 | [0.126, 0.290] | <0.001 | **yes** |
| kg_only − rag_only, faithful F1 | −0.005 | [−0.120, 0.102] | 0.943 | no |
| kg_only − rag_only, deontic align. | +0.160 | [0.082, 0.241] | <0.001 | **yes** |

**Reading these honestly.** The hybrid system beats dense retrieval on citation
faithfulness and on normative force, both significantly. The graph *alone* does
not beat dense retrieval on citation F1 — the difference is indistinguishable
from zero. The graph's independent contribution is deontic: it is the only arm
that carries normative force (obligation / prohibition / permission) as
structured data rather than inferring it from prose. `kg_only` also has the
highest hallucination rate (0.074), which is what motivated the faithful metric
in the first place.

Per-group breakdown in `results/evaluation/summary_by_group.csv`. Groups C, F
and G have n ≤ 5 and are flagged `warn_small_n`; treat them as indicative.

Absolute figures are bounded by gold-standard correctness and are **provisional
pending independent legal verification**; the relative comparisons between arms
are the claim. See `docs/gold_standard_audit.md` for the audit that corrected
seven substantive errors in an earlier draft of the gold standard.

---

## Repository layout

```
kep_fall/
├── config.py                     # all paths and env — single source of truth
├── citation.py                   # canonical article id shared by all 3 stores
│
├── phase_a_corpus/
│   ├── parse_eu_gdpr_aiact.py    # GDPR + EU AI Act -> provision chunks
│   └── parse_uk_mdr_duaa.py      # UK MDR + EU MDR + DUAA -> provision chunks
│
├── phase_b_ontology/             # DPV extension, v1 -> v4, HermiT-validated
│   ├── step1_mine_and_align.py   # candidate concepts, TF-IDF + LLM alignment
│   ├── step2_reparent_classes.py # re-parent orphans, dedup
│   ├── step3_port_restrictions.py# port v1 restrictions forward (deterministic)
│   └── step4_llm_restrictions.py # LLM-proposed OWL restrictions, validated
│
├── phase_c_graph/
│   ├── step1_build_vocab_index.py# embed ontology classes
│   ├── step2_candidate_classes.py# top-K classes per article
│   ├── step3_extract_triples.py  # schema-constrained extraction (LLM-as-typer)
│   ├── step4_reconcile_triples.py# reconcile, sanitise, validate
│   ├── step5_load_graph.py       # load Neo4j, annotate deontic + canonical id
│   └── validate_graph.py         # structural / coverage / provenance queries
│
├── phase_d_engine/
│   ├── router.py                 # question -> QueryPayload (intent + concepts)
│   ├── vector_store.py           # Chroma index build + dense retrieval
│   ├── engine.py                 # graph retrieval, context assembly, synthesis
│   ├── api.py                    # FastAPI, POST /query
│   ├── history.py                # SQLite conversation store
│   └── web/                      # static front-end
│
└── phase_e_eval/
    ├── harness.py                # ablation runner, resumable, seeded
    ├── report.py                 # results -> CSVs
    └── context_audit/            # context-budget audit (found the truncation defect)

data/
├── raw/          # source PDFs (not in git — see docs/DATA_SOURCES.md)
├── corpus/       # Phase A output
├── ontology/     # Phase B output, v1–v4
├── graph/        # Phase C intermediates
├── eval/         # competency questions + gold standard
└── cache/        # checkpoints, LLM caches

results/
├── evaluation/   # ablation results + CSVs  ← dissertation evidence
├── context_audit/
└── build_logs/

scripts/          # verify_setup.py, trace_kg.py
tests/            # pytest
docs/
```

---

## Setup

```bash
git clone <repo> && cd kep_fall
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in GROQ_API_KEY and NEO4J_*
```

The vector index is not in the repository and must be built once before the
API will run:

```bash
make index      # python -m kep_fall.phase_d_engine.vector_store
make verify     # preflight: credentials, graph schema, index
make api        # http://localhost:7860
```

`make help` lists every pipeline target.

### Rebuilding from source

Only needed if you are reproducing the build rather than running the system.
Requires the five source PDFs in `data/raw/` and the DPV 2.2.1 release in
`vendor/` (see `docs/DATA_SOURCES.md`).

```bash
make corpus     # Phase A
make ontology   # Phase B  — LLM calls, slow
make graph      # Phase C  — LLM calls, slow, checkpointed
make index      # Phase D
```

### Evaluation

```bash
make eval       # full ablation; resumable — re-run to continue after interruption
make report     # regenerate CSVs from the checkpoint
```

`python -m kep_fall.phase_e_eval.harness --reset` restarts from scratch;
`--group A` runs one group.

---

## Retrieval modes

| Mode | Uses | Role |
|---|---|---|
| `hybrid` | graph + vector store | production; the full system |
| `kg_only` | graph traversal only | isolates the graph's standalone value |
| `rag_only` | dense retrieval only | the baseline being tested against |

The harness additionally supports `kg_typed_only` / `kg_untyped_only` for the
ontology ablation.

---

## Debugging

`scripts/trace_kg.py` walks a question through every stage of graph retrieval —
router payload, keyword derivation, the exact Cypher with bound parameters, raw
hits, ranked hits with scores, and the assembled context block. It does not call
the LLM, so it is free to run.

```bash
python scripts/trace_kg.py "What lawful bases justify processing health data?"
```

This tool is how the five retrieval defects in the evaluation report were
diagnosed.

---

## License

Academic project submitted for assessment. All rights reserved; not licensed for
commercial use. Source legislation is reproduced under the terms of the
respective publishers.