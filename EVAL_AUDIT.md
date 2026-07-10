# SHIELD — Evaluation Set Audit and Rewrite (v4)

Audit date: 2026-07-10. Corpus: `regulatory_chunks.json` (559 sub-point chunks,
55 article-level chunks), `data/clean_triples.json` (618 triples, 55 articles).

Every claim below was checked against the statutory text held in the corpus.
For UK MDR 2002 and DUAA 2025 that text **is** the primary source, parsed from
legislation.gov.uk, so those corrections are grounded rather than recalled.

---

## 1. Errors found in v3

### Structurally unanswerable questions

| Q | Asked for | Status |
|---|---|---|
| A10 | GDPR Art. 30 | **Not in corpus, not in ChromaDB, not in the KG** |
| A11 | GDPR Arts. 33, 34 | **Not in corpus, not in ChromaDB, not in the KG** |

Indexed GDPR articles are only 5, 6, 7, 9, 13, 14, 15, 16, 17, 18, 22, 25, 32, 35.
These two questions could never score above zero. Their F1 of 0.000 was measuring
a **corpus gap**, not a retrieval failure. Any reported GDPR-group F1 in prior runs
is depressed by roughly 13% for this reason alone.

### Fabricated expected answers (DUAA 2025)

**F58 — Article 22B.** v3 expected "contest the decision, request human review,
express their point of view." Those are the **Article 22C** safeguards. The actual
22B is a *special-category-data* restriction:

> 22B(1): A significant decision based entirely or partly on processing described
> in Article 9(1) may not be taken based solely on automated processing, unless one
> of the following conditions is met.
> 22B(2) first condition: explicit consent.
> 22B(3) second condition: necessary for a contract, or required or authorised by
> law, **and** point (g) of Article 9(2) applies.
> 22B(4): may not be solely automated if processing relies on Article 6(1)(ea).

**F60 — Schedule 6.** v3 expected "exemptions for authorised statistical or
scientific research; **minor data subjects** have enhanced protections."

The Schedule is titled *"Automated decision-making: **minor and consequential
amendments**."* "Minor" means *small*, not *children*. The Schedule amends UK GDPR
Article 12 so cross-references to "Articles 15 to 22" reflect new Articles 22A–22D.
It contains no exemptions at all. The v3 answer was invented from a misread title.

**F57 — Article 22A.** v3 added "including decisions about eligibility for services
or assessments of personal characteristics." Not in 22A, which says only *legal
effect* or *similarly significant effect*.

**Gap:** Article 22D is in the corpus and the KG but no question tested it.

### Wrong provision cited (UK MDR 2002)

**E52 — Regulation 8.** v3: essential requirements "are in Schedule 1."
Reg 8(1) actually reads:

> no person shall place on the market or put into service a relevant device unless
> that device meets those essential requirements set out in **Annex I** which apply
> to it and the requirements set out in Regulation (EU) No 722/2012

**E53 — Regulation 9.** v3 asked about conformity assessment and UKCA marking.
Reg 9 concerns none of that. It says: intended purpose is taken into account when
determining relevant essential requirements (9(1)); clinical data must be
established per **Annex X** (9(2)); packaging and label information per Annex I
Sections 8.7 and 13 (9(3)). UKCA marking does not appear in the indexed text.

**E56** referred to "essential requirements under **Art.**8" in a UK instrument
that uses *Regulations*, not Articles.

### Structural defects in the gold standard

- Duplicate `chunk_id`s: `EUMDR_Art61` ×2, `DUAA_ArtS80-22B` ×2.
- `ANN_025` keyed on `EUAI_AnnexIII_Point5`; the ChromaDB id is `EUAI_ArtAnnexIII`.
  That annotation **never joined** and was silently dropped from every score.
- `ANN_001`–`ANN_025` used paragraph-level ids (`GDPR_Art5_Para1`) which do not
  exist in ChromaDB; they survived only because `_to_article_level()` truncated them.
- Deontic annotation covered **18 of 55** articles. Every `deontic_align` figure in
  prior runs was computed on a third of the corpus.

### Metric defects

- `kg_hit_rate = 1.000` measured *"did Cypher return any row"*, not *"the right
  row."* A metric that returns 1.0 for every input has no discriminative power.
- `intent_acc = 1.000` on 59/60 `knowledge` questions. A classifier that always
  outputs "knowledge" scores 0.983. There were no negative examples.
- `concept_cov` used lexical substring matching: "lawful basis" vs "legal basis" → 0.
- `deontic_align` returned `None` for `kg_only`, making that arm uncomparable.
- No hallucination metric, despite the slide promising one.
- No significance testing. Group C swung 0.10 between runs with no code change.

### Missing content

The slide promises four scenario systems — fall-risk AI, fitness tracker, hospital
triage, anonymisation boundary case. None existed in the question set.

---

## 2. What v4 changes

### `eval_questions_full.json` — 60 → 65 questions

| Group | n | Change |
|---|---|---|
| A GDPR | 15 | A10 → Art. 16 (rectification). A11 → Art. 9(2) exceptions. Both now answerable. |
| B EU AI Act | 18 | Expected answers restated from statutory text. B21 reworded from "why" to the legal rule. |
| C cross-reg | 5 | Unchanged in scope; answers expanded. |
| D EU MDR | 10 | D46 retargeted to Art. 2 **+ Annex VIII Rule 11**, giving it a citation set distinct from D39. |
| E UK MDR | 8 | E51 adds the Secretary-of-State dispute route. **E52 corrected to Annex I.** **E53 fully retargeted.** E55 rewritten to Part 4A scope. E56 "Art. 8" → "Reg. 8". |
| F DUAA | 5 | **F57, F58 corrected. F60 replaced with Art. 22D** (previously untested). New F61 covers Schedule 6 correctly. |
| G scenario | 4 | **New.** G62 fall-risk, G63 fitness tracker, G64 triage, G65 anonymisation. |

New fields: `group`, `intent`, `article_ids` (canonical, machine-checked),
`expected_regulations` (scenarios), `verification`.

`intent` is now `knowledge` (61) / `scenario` (4), so `intent_acc` finally has
negative examples and means something.

### `gold_standard_full.json` — 45 → 55 annotations

- Join key is `article_id`, **derived from the corpus at build time**, never typed
  by hand. It cannot drift from ChromaDB or the KG.
- Deontic coverage **18/55 → 55/55**.
- Duplicates removed; `EUAI_ArtAnnexIII` fixed; paragraph ids normalised.
- New `amendment` deontic type for Schedule 6, which is neither obligation,
  prohibition, permission nor classification rule.
- `annotator_note` records where the source text's deontic force differs from the
  recorded type (e.g. UKMDR Reg 8 is literally a conditional prohibition,
  "no person shall … unless", recorded as `obligation` because the operative duty
  is compliance with Annex I).

Validation, all passing:

```
gold annotations            : 55
duplicate article_ids       : none
gold ⊆ ChromaDB             : True
gold ⊆ KG                   : True
kg_article_id round-trips   : True
every question article has gold : True
ChromaDB articles == KG articles : True (55 each)
```

### `p2_step5_aura_graph.py`

Adds to every `:REL` edge:

- `r.deontic` — obligation / prohibition / permission / classification_rule / amendment
- `r.deontic_source` — `gold` | `predicate` | `none`
- `r.canonical_id` — one join key across Neo4j, ChromaDB and the gold standard

Because gold now covers 55/55 articles, **all 618 edges resolve `deontic` from
gold**; the predicate fallback never fires. This matters: the DPV predicate
vocabulary has no term meaning *prohibition*, so a predicate-derived label could
never have produced the 44 prohibition edges the graph now carries.

`ON MATCH SET` was added so a corrected gold annotation propagates on re-run.
Without it, an already-loaded graph would keep the old label forever.

A structural-statistics query is emitted at the end (nodes, edges, typed nodes,
average degree, density), following Turaga et al., IEEE Access 2025, Table 2.

### `eval_p5.py`

| Old | New |
|---|---|
| `kg_hit_rate` (saturated at 1.0) | `answerability` — does the KG return a triple on the **gold** article? |
| `concept_cov` (substring) | embedding cosine, threshold 0.60 |
| `deontic_align` = None for kg_only | reads `r.deontic`; every arm scorable |
| — | `hallucination` = cited-but-not-retrieved rate |
| — | `regulation_f1` for scenario questions |
| — | paired bootstrap, 5000 resamples, seed 20260710 |
| 3 arms | 9 arms in a registry: retrieval, ontology, provenance, confidence sweep |

Scenario questions are scored on **regulation-set F1, not article F1**. "Which laws
apply" is a different question from "which article says so," and G63/G65 test correct
*exclusion* — an over-inclusive answer is penalised on precision.

The harness now **raises** if any `article_id` lacks a gold annotation, rather than
silently scoring zero. That check is what would have caught A10 and A11.

---

## 3. Run order

```bash
# 1. reload the graph so edges carry deontic + canonical_id
python p2_step5_aura_graph.py

# 2. self-test the normaliser (should print ALL PASS)
python citation_norm.py

# 3. smoke test on two groups before spending the full budget
python eval_p5.py --arms hybrid kg_only rag_only --groups A F --reset

# 4. headline retrieval ablation
python eval_p5.py --arms hybrid kg_only rag_only --reset

# 5. full ablation
python eval_p5.py
```

`rag.py` does **not** need rebuilding — the corpus is unchanged. Only the graph
reload (step 1) is required, because the edge schema changed.

Step 5 is 65 questions × 9 arms × ~2.5 s ≈ 25 minutes of Groq calls.
The checkpoint file makes it resumable.

---

## 4. What is still not verified

I checked deontic type, actor, action and condition against the statutory text in
the corpus. That is a genuine primary source for UK MDR and DUAA, and article-level
text for GDPR / EU AI Act / EU MDR.

It is **not** a substitute for legal review. Specifically:

- The four scenario questions (G62–G65) are marked `needs_legal_review`. Whether a
  fall-risk predictor is a Class IIa device under Rule 11, and whether a consumer
  fitness tracker escapes the MDR, are judgement calls a regulatory affairs
  specialist should confirm.
- G65's fully correct answer would cite GDPR Art. 4(1) and Recital 26 on anonymous
  data. **Art. 4 is not in the indexed corpus.** The question is therefore scored on
  regulation set only, and the `article_ids` point at Arts. 5, 25, 32, which govern
  the anonymisation *process*. This is a documented limitation, not a fix.
- Ten corpus articles remain unexercised: EUAI Arts. 17–21, 29, 51–53, Annex IV.

Until an independent reviewer signs off on all 65, **absolute F1 values are
provisional**. Claim the *relative ordering between arms* — that is what the paired
bootstrap licenses — and say so explicitly in the thesis.

---

## 5. Borrowed from Turaga et al. (CO2, IEEE Access 2025)

**Adopted.** Structural graph metrics (nodes, edges, average degree, density,
weakly-connected components) as a one-off characterisation table. Their key finding
is that NER-derived graphs scored **Relevancy = 0.0000** — compliance-specific
relations entirely absent — which is what justified moving to LLM extraction. Their
deontic `type: SHALL_DO` edge property is the direct precedent for `r.deontic`.

**Rejected.** Their compliance-check Cypher queries as an *evaluation method*. They
have no gold standard. They report that their missing-penalty query returned nothing
and that they could not determine whether this meant Chapter III is compliant or
that their query failed to match the extracted patterns. That ambiguity is
disqualifying. Citation-F1 against a verified gold standard is strictly stronger.

Worth stating in the thesis: they evaluate **Article 6 of one regulation**.
SHIELD evaluates 65 questions across **five** regulations.
