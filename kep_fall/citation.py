"""
citation_norm.py — one canonical article identifier, used everywhere.

The three stores disagree on how they name an article:

    Neo4j   r.article_id   "EU AI Act__ArtAnnex III"
    Chroma  chunk_id       "EUAI_ArtAnnexIII"
    gold    article_id     "EUAI_ArtAnnexIII"

Everything reduces to the Chroma form, which is canonical. This removes the
prose-regex path from the PRIMARY scoring route. extract_from_prose() survives
only as a fallback for when the model emits no structured citations.
"""
import re

PREFIX = {
    "GDPR":            "GDPR",
    "EU AI Act":       "EUAI",
    "EU MDR 2017/745": "EUMDR",
    "UK MDR 2002":     "UKMDR",
    "DUAA 2025":       "DUAA",
}

ALIAS = {
    "gdpr": "GDPR", "uk gdpr": "GDPR", "eu gdpr": "GDPR",
    "eu ai act": "EU AI Act", "ai act": "EU AI Act", "euai": "EU AI Act",
    "eu mdr": "EU MDR 2017/745", "eu mdr 2017/745": "EU MDR 2017/745",
    "mdr": "EU MDR 2017/745", "eumdr": "EU MDR 2017/745",
    "uk mdr": "UK MDR 2002", "uk mdr 2002": "UK MDR 2002", "ukmdr": "UK MDR 2002",
    "duaa": "DUAA 2025", "duaa 2025": "DUAA 2025",
    "data (use and access) act 2025": "DUAA 2025",
}


def _reg(name: str) -> str:
    if not name:
        return ""
    return ALIAS.get(name.strip().lower(), name.strip())


def _art_safe(article: str) -> str:
    return article.replace(" ", "").replace("/", "-").replace(".", "_")


def canonical(regulation: str, article: str) -> str:
    """('EU AI Act', 'Annex III') -> 'EUAI_ArtAnnexIII'"""
    reg = _reg(regulation)
    return f"{PREFIX.get(reg, reg.replace(' ', ''))}_Art{_art_safe(article)}"


def canonical_from_kg(article_id: str) -> str:
    """'EU AI Act__ArtAnnex III' -> 'EUAI_ArtAnnexIII'  (Neo4j r.article_id)"""
    if not article_id:
        return ""
    reg, sep, rest = article_id.partition("__")
    if not sep:
        return article_id.replace(" ", "")
    return f"{PREFIX.get(_reg(reg), reg.replace(' ', ''))}_{rest.replace(' ', '')}"


def canonical_from_chunk(chunk_id: str) -> str:
    """Chroma ids are already canonical (rag.py aggregates to article level)."""
    return chunk_id or ""


# ── prose fallback ───────────────────────────────────────────────────────
# DUAA must run FIRST and its matched span must be blanked, otherwise the
# generic Article pattern re-grabs the bare "22" out of "Article 22C".

_DUAA  = re.compile(r"(?:Art(?:icle)?\.?\s*)?(?:S80[-\s]*)?(22[ABCD])\b", re.I)
_ART   = re.compile(r"Art(?:icle)?\.?\s*([0-9]{1,3})", re.I)
_REG   = re.compile(r"Reg(?:ulation)?\.?\s*([0-9]{1,3}[A-Z]?)", re.I)
_ANNEX = re.compile(r"Annex\s+([IVXL]+)", re.I)
_SCHED = re.compile(r"Schedule\s+([0-9]+)", re.I)
_PART  = re.compile(r"Part\s+([0-9]+[A-Z]?)", re.I)


def extract_from_prose(text: str, default_regulation: str) -> set:
    """Fallback only. Returns canonical ids."""
    if not text:
        return set()
    reg, work, found = _reg(default_regulation), text, set()

    if reg == "DUAA 2025":
        for m in _DUAA.finditer(work):
            found.add(canonical(reg, f"S80-{m.group(1).upper()}"))
        work = _DUAA.sub(" ", work)
        for m in _SCHED.finditer(work):
            found.add(canonical(reg, f"Schedule {m.group(1)}"))
        return found

    if reg == "UK MDR 2002":
        for m in _PART.finditer(work):
            found.add(canonical(reg, f"Part{m.group(1).upper()}"))
        work = _PART.sub(" ", work)
        for m in _REG.finditer(work):
            found.add(canonical(reg, m.group(1)))
        return found

    for m in _ANNEX.finditer(work):
        found.add(canonical(reg, f"Annex {m.group(1).upper()}"))
    work = _ANNEX.sub(" ", work)
    for m in _ART.finditer(work):
        found.add(canonical(reg, m.group(1)))
    return found


if __name__ == "__main__":
    checks = [
        (canonical_from_kg("GDPR__Art5"),                  "GDPR_Art5"),
        (canonical_from_kg("EU AI Act__ArtAnnex III"),     "EUAI_ArtAnnexIII"),
        (canonical_from_kg("EU MDR 2017/745__ArtAnnex I"), "EUMDR_ArtAnnexI"),
        (canonical_from_kg("UK MDR 2002__ArtPart4A"),      "UKMDR_ArtPart4A"),
        (canonical_from_kg("DUAA 2025__ArtS80-22A"),       "DUAA_ArtS80-22A"),
        (canonical_from_kg("DUAA 2025__ArtSchedule 6"),    "DUAA_ArtSchedule6"),
        (canonical("UK MDR 2002", "Part4A"),               "UKMDR_ArtPart4A"),
    ]
    ok = True
    for got, want in checks:
        good = got == want
        ok &= good
        print(("OK  " if good else "FAIL"), f"{got:20} | {want}")

    p = extract_from_prose("Article 22C requires safeguards; see also 22B.", "DUAA 2025")
    no_bare = "DUAA_Art22" not in p
    ok &= no_bare and p == {"DUAA_ArtS80-22B", "DUAA_ArtS80-22C"}
    print(("OK  " if no_bare else "FAIL"), "prose DUAA ->", sorted(p))

    u = extract_from_prose("Regulation 8 requires Annex I; see Part 4A.", "UK MDR 2002")
    print("OK  " if u == {"UKMDR_Art8", "UKMDR_ArtPart4A"} else "FAIL", "prose UKMDR ->", sorted(u))
    print("\nALL PASS" if ok else "\nFAILURES")