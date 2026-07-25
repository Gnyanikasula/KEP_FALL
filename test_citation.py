"""
Unit tests for kep_fall.citation — the canonical article identifier.

This module is the join key between three stores that each name articles
differently (Neo4j r.article_id, Chroma chunk_id, the gold standard). If it
drifts, every citation metric in Phase E silently mis-scores, so it is the one
piece of the codebase that genuinely warrants tests.

Replaces the previous scratch file `test.py`, which printed results to stdout
for eyeballing and asserted nothing.

Run:  pytest -q
"""

import pytest

from kep_fall.citation import canonical, canonical_from_chunk, canonical_from_kg


class TestCanonicalFromKg:
    """Neo4j form: '<Regulation Name>__Art<N>' -> '<PREFIX>_Art<N>'."""

    @pytest.mark.parametrize(
        "kg_id, expected",
        [
            ("GDPR__Art9", "GDPR_Art9"),
            ("EU AI Act__Art6", "EUAI_Art6"),
            ("EU AI Act__ArtAnnex III", "EUAI_ArtAnnexIII"),
            ("EU MDR 2017/745__Art10", "EUMDR_Art10"),
            ("UK MDR 2002__Reg5", "UKMDR_Reg5"),
            ("DUAA 2025__ArtS80-22B", "DUAA_ArtS80-22B"),
        ],
    )
    def test_known_regulations(self, kg_id, expected):
        assert canonical_from_kg(kg_id) == expected

    def test_empty_input_returns_empty(self):
        assert canonical_from_kg("") == ""

    def test_missing_separator_is_passed_through_despaced(self):
        # Defensive: an id without '__' should not raise.
        assert canonical_from_kg("GDPR Art9") == "GDPRArt9"


class TestCanonicalFromChunk:
    """Chroma form is already canonical; the function must be a no-op on it."""

    @pytest.mark.parametrize(
        "chunk_id",
        ["GDPR_Art9", "EUAI_ArtAnnexIII", "UKMDR_Reg5", "DUAA_ArtS80-22B"],
    )
    def test_idempotent_on_canonical_form(self, chunk_id):
        assert canonical_from_chunk(chunk_id) == chunk_id


class TestCrossStoreAgreement:
    """
    The property that actually matters: the same provision reached from the
    graph and from the vector store must produce one identifier. This is the
    invariant the whole citation-F1 metric rests on.
    """

    @pytest.mark.parametrize(
        "kg_id, chunk_id",
        [
            ("GDPR__Art9", "GDPR_Art9"),
            ("EU AI Act__ArtAnnex III", "EUAI_ArtAnnexIII"),
            ("UK MDR 2002__Reg5", "UKMDR_Reg5"),
        ],
    )
    def test_graph_and_vector_ids_converge(self, kg_id, chunk_id):
        assert canonical_from_kg(kg_id) == canonical_from_chunk(chunk_id)


class TestCanonical:
    def test_builds_from_parts(self):
        assert canonical("GDPR", "9") == "GDPR_Art9"

    def test_annex_spaces_are_stripped(self):
        assert canonical("EU AI Act", "Annex III") == "EUAI_ArtAnnexIII"

    def test_regulation_alias_is_case_insensitive(self):
        assert canonical("gdpr", "9") == canonical("GDPR", "9")