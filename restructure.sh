#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# KEP_FALL — repository restructure, gny_v3 -> phase-aligned layout.
#
# Run from the repo root, on a NEW branch:
#     git checkout -b chore/restructure
#     bash restructure.sh
#     git status          # review before committing
#
# Uses `git mv` throughout so file history survives the rename. Nothing is
# deleted without being staged as a deletion you can review.
# ---------------------------------------------------------------------------
set -euo pipefail

if [ ! -d .git ]; then
  echo "ERROR: run this from the repository root (no .git found)."; exit 1
fi
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" = "gny" ] || [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  echo "ERROR: you are on '$BRANCH'. Create a branch first:"
  echo "         git checkout -b chore/restructure"; exit 1
fi

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
mv_() { # git mv when tracked, plain mv when not, skip when absent
  if [ ! -e "$1" ]; then echo "   SKIP (absent): $1"; return 0; fi
  if git ls-files --error-unmatch "$1" >/dev/null 2>&1; then
    git mv "$1" "$2" && echo "   $1  ->  $2  (tracked)"
  else
    mv "$1" "$2"     && echo "   $1  ->  $2  (UNTRACKED — check .gitignore)"
  fi
}

# ---------------------------------------------------------------------------
say "1/8  Creating directory skeleton"
mkdir -p kep_fall/phase_a_corpus \
         kep_fall/phase_b_ontology \
         kep_fall/phase_c_graph \
         kep_fall/phase_d_engine/web \
         kep_fall/phase_e_eval/context_audit \
         data/raw data/corpus data/ontology data/graph data/eval data/cache \
         results/evaluation results/context_audit results/build_logs \
         scripts tests docs

# ---------------------------------------------------------------------------
say "2/8  Phase A — corpus construction (was: parser*.py)"
mv_ parser.py            kep_fall/phase_a_corpus/parse_eu_gdpr_aiact.py
mv_ parser_mda_duaa.py   kep_fall/phase_a_corpus/parse_uk_mdr_duaa.py

say "     Phase B — ontology engineering (was: onto_construct.py, p1_*.py)"
mv_ onto_construct.py       kep_fall/phase_b_ontology/step1_mine_and_align.py
mv_ p1_cleanup.py           kep_fall/phase_b_ontology/step2_reparent_classes.py
mv_ p1_fix.py               kep_fall/phase_b_ontology/step3_port_restrictions.py
mv_ p1_llm_restrictions.py  kep_fall/phase_b_ontology/step4_llm_restrictions.py

say "     Phase C — knowledge-graph population (was: p2_step*.py, graph_val.py)"
mv_ p2_step1.py             kep_fall/phase_c_graph/step1_build_vocab_index.py
mv_ p2_step2.py             kep_fall/phase_c_graph/step2_candidate_classes.py
mv_ p2_step3.py             kep_fall/phase_c_graph/step3_extract_triples.py
mv_ p2_step4.py             kep_fall/phase_c_graph/step4_reconcile_triples.py
mv_ p2_step5_aura_graph.py  kep_fall/phase_c_graph/step5_load_graph.py
mv_ graph_val.py            kep_fall/phase_c_graph/validate_graph.py

say "     Phase D — retrieval & synthesis engine (was: route/rag/verdict/api)"
mv_ route.py     kep_fall/phase_d_engine/router.py
mv_ rag.py       kep_fall/phase_d_engine/vector_store.py
mv_ verdict.py   kep_fall/phase_d_engine/engine.py
mv_ api.py       kep_fall/phase_d_engine/api.py
mv_ history.py   kep_fall/phase_d_engine/history.py
mv_ static/index.html kep_fall/phase_d_engine/web/index.html
mv_ static/app.js     kep_fall/phase_d_engine/web/app.js
mv_ static/style.css  kep_fall/phase_d_engine/web/style.css
rmdir static 2>/dev/null || true

say "     Phase E — evaluation (was: eval_p5.py, summarize_results.py, phase0_*)"
mv_ eval_p5.py            kep_fall/phase_e_eval/harness.py
mv_ summarize_results.py  kep_fall/phase_e_eval/report.py
mv_ phase0_cache_payloads.py kep_fall/phase_e_eval/context_audit/step1_cache_payloads.py
mv_ phase0_chunk_stats.py    kep_fall/phase_e_eval/context_audit/step2_chunk_stats.py
mv_ phase0_audit.py          kep_fall/phase_e_eval/context_audit/step3_retrieval_audit.py

say "     Shared + tooling"
mv_ citation_norm.py  kep_fall/citation.py
mv_ verify_setup.py   scripts/verify_setup.py
mv_ kg_trace.py       scripts/trace_kg.py

# ---------------------------------------------------------------------------
say "3/8  Data artefacts"
mv_ regulatory_chunks.json  data/corpus/regulatory_chunks.json

mv_ OUT_CANDIDATES/candidate_concepts.json   data/ontology/candidate_concepts.json
mv_ OUT_CANDIDATES/alignment_results.json    data/ontology/alignment_results.json
mv_ OUT_CANDIDATES/classes_created.json      data/ontology/classes_created.json
mv_ OUT_CANDIDATES/classes_created_v2.json   data/ontology/classes_created_v2.json
mv_ OUT_CANDIDATES/dedup_report.json         data/ontology/dedup_report.json
mv_ OUT_CANDIDATES/llm_restrictions_raw.json data/ontology/llm_restrictions_raw.json
mv_ OUT_CANDIDATES/dpv-fallrisk-ext.rdf      data/ontology/dpv-fallrisk-ext-v1.rdf
mv_ OUT_CANDIDATES/dpv-fallrisk-ext-v2.rdf   data/ontology/dpv-fallrisk-ext-v2.rdf
mv_ OUT_CANDIDATES/dpv-fallrisk-ext-v3.rdf   data/ontology/dpv-fallrisk-ext-v3.rdf
mv_ OUT_CANDIDATES/dpv-fallrisk-ext-v4.rdf   data/ontology/dpv-fallrisk-ext-v4.rdf

mv_ data/vocab_index.json          data/graph/vocab_index.json
mv_ data/articles_with_classes.json data/graph/articles_with_classes.json
mv_ data/validated_triples.json    data/graph/validated_triples.json
mv_ data/clean_triples.json        data/graph/clean_triples.json

mv_ eval_questions_full.json  data/eval/competency_questions.json
mv_ gold_standard_full.json   data/eval/gold_standard.json

mv_ summary_cache.json                data/cache/article_summaries.json
mv_ checkpoints/step3_checkpoint.json data/cache/triple_extraction_checkpoint.json
rmdir checkpoints 2>/dev/null || true

# ---------------------------------------------------------------------------
say "4/8  Results and build logs"
mv_ Results/eval_p5_results.json          results/evaluation/ablation_results.json
mv_ Results/eval_p5_checkpoint.json       results/evaluation/ablation_checkpoint.json
mv_ Results/eval_p5_results_PRE_FIX.json  results/evaluation/ablation_results_pre_retrieval_fix.json
mv_ Results/summary_by_arm.csv            results/evaluation/summary_by_arm.csv
mv_ Results/summary_by_group.csv          results/evaluation/summary_by_group.csv
mv_ Results/per_question.csv              results/evaluation/per_question.csv
mv_ Results/bootstrap_cis.csv             results/evaluation/bootstrap_cis.csv
rmdir Results 2>/dev/null || true

mv_ phase0_out/payloads.json        results/context_audit/cached_payloads.json
mv_ phase0_out/chunk_stats.json     results/context_audit/chunk_stats.json
mv_ phase0_out/audit_summary.json   results/context_audit/audit_summary.json
mv_ phase0_out/retrieval_dump.json  results/context_audit/retrieval_dump.json
rmdir phase0_out 2>/dev/null || true

mv_ logs/step1_report.txt            results/build_logs/phase_c_step1_vocab_index.txt
mv_ logs/step4_report.txt            results/build_logs/phase_c_step4_reconcile.txt
mv_ logs/step6_validation_report.txt results/build_logs/phase_c_graph_validation.txt
mv_ OUT_CANDIDATES/build_log.md      results/build_logs/phase_b_step1_mine_and_align.md
mv_ OUT_CANDIDATES/cleanup_log.md    results/build_logs/phase_b_step2_reparent.md
mv_ OUT_CANDIDATES/fix_log.md        results/build_logs/phase_b_step3_port_restrictions.md
mv_ OUT_CANDIDATES/llm_restrictions_log.md results/build_logs/phase_b_step4_llm_restrictions.md
rmdir logs OUT_CANDIDATES 2>/dev/null || true

say "     Docs"
mv_ EVAL_AUDIT.md docs/gold_standard_audit.md

# ---------------------------------------------------------------------------
say "5/8  Removing dead files (staged as deletions — review before commit)"
# eval_p4.py is byte-identical to eval_p5.py. One harness, not two.
[ -e eval_p4.py ]        && git rm -q eval_p4.py        && echo "   deleted eval_p4.py (duplicate of eval_p5.py)"
# One-shot source-rewriting migration script; its effect is already in engine.py.
[ -e apply_v3_patch.py ] && git rm -q apply_v3_patch.py && echo "   deleted apply_v3_patch.py (spent migration)"
# Scratch REPL file; replaced by tests/test_citation.py
[ -e test.py ]           && git rm -q test.py           && echo "   deleted test.py (scratch, replaced by tests/)"
true

# ---------------------------------------------------------------------------
say "6/8  Package markers"
for d in kep_fall kep_fall/phase_a_corpus kep_fall/phase_b_ontology kep_fall/phase_c_graph \
         kep_fall/phase_d_engine kep_fall/phase_e_eval kep_fall/phase_e_eval/context_audit tests; do
  [ -f "$d/__init__.py" ] || : > "$d/__init__.py"
done
echo "   __init__.py written into 8 packages"

# ---------------------------------------------------------------------------
say "7/8  Rewriting intra-project imports"
py_files=$(git ls-files '*.py'; find kep_fall scripts tests -name '*.py' 2>/dev/null)
for f in $(echo "$py_files" | sort -u); do
  [ -f "$f" ] || continue
  # Leading-whitespace group is preserved, so imports nested inside functions
  # (there are three) are rewritten with their indentation intact.
  sed -i -E \
    -e 's/^([[:space:]]*)from route import/\1from kep_fall.phase_d_engine.router import/' \
    -e 's/^([[:space:]]*)from verdict import/\1from kep_fall.phase_d_engine.engine import/' \
    -e 's/^([[:space:]]*)import verdict as V$/\1from kep_fall.phase_d_engine import engine as V/' \
    -e 's/^([[:space:]]*)from history import/\1from kep_fall.phase_d_engine.history import/' \
    -e 's/^([[:space:]]*)from citation_norm import/\1from kep_fall.citation import/' \
    -e 's/^([[:space:]]*)from rag import/\1from kep_fall.phase_d_engine.vector_store import/' \
    "$f"
done
echo "   done"
echo "   verify: grep -rn 'from route \|from verdict \|import verdict\|from citation_norm\|from rag import' --include='*.py' ."

# ---------------------------------------------------------------------------
say "8/9  Renaming SHIELD -> KEP_FALL in source (identity strings + env vars)"
# SHIELD was a personal-project name that leaked into this codebase: header
# comments, env-var prefixes (SHIELD_RAG_HEAD_N ...), and — importantly —
# user-facing strings the assistant says back to people ("Here are some
# questions you can ask SHIELD"). All of it becomes KEP_FALL.
sweep=$(git ls-files '*.py' '*.js' '*.css' '*.html' '*.md'; \
        find kep_fall scripts tests -type f \( -name '*.py' -o -name '*.js' \
             -o -name '*.css' -o -name '*.html' \) 2>/dev/null)
for f in $(echo "$sweep" | sort -u); do
  [ -f "$f" ] || continue
  sed -i -E 's/\bSHIELD_/KEP_FALL_/g; s/\bSHIELD\b/KEP_FALL/g' "$f"
done
echo "   swept .py/.js/.css/.html/.md"
echo "   NOTE: env-var names changed (SHIELD_RAG_HEAD_N -> KEP_FALL_RAG_HEAD_N)."
echo "         If you set any of these in .env, rename them there too."

# ---------------------------------------------------------------------------
say "9/9  Keeping empty output dirs in git"
for d in data/raw results/evaluation results/context_audit results/build_logs; do
  [ -f "$d/.gitkeep" ] || : > "$d/.gitkeep"
done

say "DONE — structure moved. NOT yet committed."
cat <<'EOF'

  Remaining manual work (see docs/RESTRUCTURE_NOTES.md):
    1. Drop kep_fall/config.py in place, then replace the hard-coded path
       constants at the top of each moved script with imports from it.
    2. Replace requirements.txt with the trimmed version.
    3. Update Dockerfile CMD + .dockerignore paths.
    4. Add .env.example.
    5. Run: python scripts/verify_setup.py

  Then:  git add -A && git commit -m "chore: restructure repo into pipeline phases A-E"
EOF