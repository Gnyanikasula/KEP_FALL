# KEP_FALL - pipeline entry points, in dependency order.
# Every target is runnable from the repository root.
.PHONY: help install verify corpus ontology graph index api eval report test clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

install:   ## Install runtime + dev dependencies
	pip install -r requirements-dev.txt

verify:    ## Preflight: credentials, Neo4j schema, Chroma index
	python scripts/verify_setup.py

# offline build (run once; re-run only on a regulation update) 
corpus:    ## Phase A - parse legislation PDFs into provision chunks
	python -m kep_fall.phase_a_corpus.parse_eu_gdpr_aiact
	python -m kep_fall.phase_a_corpus.parse_uk_mdr_duaa

ontology:  ## Phase B - build and validate the DPV extension (v1 -> v4)
	python -m kep_fall.phase_b_ontology.step1_mine_and_align
	python -m kep_fall.phase_b_ontology.step2_reparent_classes
	python -m kep_fall.phase_b_ontology.step3_port_restrictions
	python -m kep_fall.phase_b_ontology.step4_llm_restrictions

graph:     ## Phase C - extract triples and load the knowledge graph
	python -m kep_fall.phase_c_graph.step1_build_vocab_index
	python -m kep_fall.phase_c_graph.step2_candidate_classes
	python -m kep_fall.phase_c_graph.step3_extract_triples
	python -m kep_fall.phase_c_graph.step4_reconcile_triples
	python -m kep_fall.phase_c_graph.step5_load_graph
	python -m kep_fall.phase_c_graph.validate_graph

index:     ## Phase D - build the Chroma vector index (required before `api`)
	python -m kep_fall.phase_d_engine.vector_store

# runtime 
api:       ## Phase D - serve the API + web UI on :7860
	uvicorn kep_fall.phase_d_engine.api:app --host 0.0.0.0 --port 7860 --reload

# evaluation
eval:      ## Phase E - run the full ablation (resumable)
	python -m kep_fall.phase_e_eval.harness

report:    ## Phase E - regenerate result CSVs from the checkpoint
	python -m kep_fall.phase_e_eval.report

test:      ## Unit tests
	pytest -q

clean:     ## Remove Python caches (leaves data/ and results/ intact)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache