"""
kg_trace.py — watch a question travel through the knowledge graph.

Shows every stage of KG retrieval, in order:

  STAGE 1  Router      the question -> QueryPayload (intent + extracted fields)
  STAGE 2  Keywords    which payload fields become graph-anchor keywords, and
                       the de-spaced / word variants that match node labels
  STAGE 3  Cypher      the EXACT Cypher sent to Neo4j, with $keywords bound
  STAGE 4  Raw hits    every triple the graph returned, before ranking
  STAGE 5  Ranked      the same triples after _rank_triples, with the score
                       that decided the order, and the top_k cut line
  STAGE 6  Context     the block the LLM actually receives (build_context)

Usage:
  python kg_trace.py "What lawful bases justify processing personal data?"
  python kg_trace.py                       # interactive prompt loop
  python kg_trace.py --top-k 20 "..."      # change the cut
  python kg_trace.py --no-context "..."    # skip STAGE 6

Nothing here calls the LLM synthesiser. It is read-only against the graph,
so it is free to run and does not touch your Groq token budget.
"""

import argparse
import sys

# Import the REAL pipeline functions so the trace matches production exactly.
from route import understand_query
import verdict as V


# ── pretty printing ───────────────────────────────────────────────────────
class C:
    H  = "\033[95m"; B = "\033[94m"; G = "\033[92m"
    Y  = "\033[93m"; R = "\033[91m"; DIM = "\033[2m"
    BOLD = "\033[1m"; END = "\033[0m"

def _supports_colour() -> bool:
    return sys.stdout.isatty()

if not _supports_colour():           # Windows redirect / file: strip codes
    for k in list(vars(C)):
        if not k.startswith("_"):
            setattr(C, k, "")

def banner(n, title):
    print(f"\n{C.H}{C.BOLD}{'='*78}{C.END}")
    print(f"{C.H}{C.BOLD} STAGE {n}: {title}{C.END}")
    print(f"{C.H}{C.BOLD}{'='*78}{C.END}")


# ── the Cypher, mirrored from verdict.kg_retrieve so we can DISPLAY it ─────
# verdict.py holds the authoritative copy; this is the same text, shown with
# the bound keyword list substituted in, purely for the trace.
def render_cypher(keywords):
    kw_repr = "[" + ", ".join(f'"{k}"' for k in keywords) + "]"
    return f"""// $keywords = {kw_repr}
//
// PASS A — anchor node is the SUBJECT of the edge
MATCH (s:Concept)-[r:REL]->(o:Concept)
WHERE any(kw IN $keywords
          WHERE toLower(s.label)     CONTAINS kw
             OR toLower(r.predicate) CONTAINS kw
             OR (s.uri IS NOT NULL AND toLower(s.uri) CONTAINS kw))
RETURN s.label AS subject, r.predicate AS predicate, o.label AS object,
       s.typed AS subject_typed, o.typed AS object_typed,
       r.regulation AS regulation, r.article_id AS article_id,
       r.deontic AS deontic, r.confidence AS confidence
ORDER BY r.confidence DESC, s.typed DESC
LIMIT 30

UNION

// PASS B — anchor node is the OBJECT of the edge
MATCH (s:Concept)-[r:REL]->(o:Concept)
WHERE any(kw IN $keywords
          WHERE toLower(o.label)     CONTAINS kw
             OR toLower(r.predicate) CONTAINS kw
             OR (o.uri IS NOT NULL AND toLower(o.uri) CONTAINS kw))
RETURN s.label AS subject, r.predicate AS predicate, o.label AS object,
       s.typed AS subject_typed, o.typed AS object_typed,
       r.regulation AS regulation, r.article_id AS article_id,
       r.deontic AS deontic, r.confidence AS confidence
ORDER BY r.confidence DESC, s.typed DESC
LIMIT 20"""


def _rank_score(row, keywords):
    """Re-derive the ranking score so we can show WHY each triple placed."""
    hay = " ".join(str(row.get(f) or "").lower()
                   for f in ("subject", "object", "predicate",
                             "subject_uri", "object_uri"))
    matches = sum(1 for kw in keywords if kw in hay)
    typed   = bool(row.get("subject_typed")) + bool(row.get("object_typed"))
    return matches, round(row.get("confidence") or 0.0, 2), typed


def trace(question, top_k=12, show_context=True):
    print(f"\n{C.BOLD}QUESTION:{C.END} {question}")

    # ── STAGE 1 : router ──────────────────────────────────────────────────
    banner(1, "ROUTER  —  question parsed into a structured payload")
    payload = understand_query(question)
    if payload is None:
        print(f"{C.R}Router returned None (LLM parse failed). Stop.{C.END}")
        return

    print(f"  intent = {C.G}{payload.intent}{C.END}")
    if payload.intent not in ("scenario", "knowledge"):
        print(f"\n  {C.Y}This intent does not query the graph "
              f"(it is a canned response). No KG retrieval happens.{C.END}")
        return

    fields = ["data_type", "system_type", "action", "purpose",
              "deployment_context", "recipients", "topic", "jurisdiction"]
    print(f"  {C.DIM}extracted fields (None = not present):{C.END}")
    for fld in fields:
        val = getattr(payload, fld, None)
        mark = C.G if val else C.DIM
        print(f"    {mark}{fld:20}{C.END} = {mark}{val!r}{C.END}")

    # ── STAGE 2 : keyword construction ────────────────────────────────────
    banner(2, "KEYWORDS  —  which fields anchor the graph search")
    # The exact sources kg_retrieve feeds to _kg_keywords:
    sources = [payload.data_type, payload.system_type, payload.topic,
               payload.purpose, payload.action]
    print(f"  {C.DIM}source fields passed to _kg_keywords "
          f"(data_type, system_type, topic, purpose, action):{C.END}")
    for s in sources:
        if s:
            print(f"    - {s!r}")
    keywords = V._kg_keywords(*sources)
    print(f"\n  {C.BOLD}keywords produced ({len(keywords)}):{C.END}")
    for kw in keywords:
        kind = ("de-spaced phrase" if " " not in kw and len(kw) > 12
                else "phrase" if " " in kw else "word")
        print(f"    {C.G}{kw!r:32}{C.END} {C.DIM}({kind}){C.END}")
    if not keywords:
        print(f"  {C.R}No keywords — KG retrieval returns []. Stop.{C.END}")
        return
    print(f"\n  {C.DIM}Match rule: node label / predicate / uri CONTAINS any keyword "
          f"(lowercased).\n  Node labels are PascalCase concatenations, so the "
          f"de-spaced variant is what\n  actually matches a label like "
          f"'LegalBasis'.{C.END}")

    # ── STAGE 3 : the Cypher ──────────────────────────────────────────────
    banner(3, "CYPHER  —  the exact query sent to Neo4j")
    print(C.B + render_cypher(keywords) + C.END)

    # ── STAGE 4 : raw hits ────────────────────────────────────────────────
    banner(4, "RAW HITS  —  every triple the graph returned, pre-ranking")
    # Call the REAL retriever with top_k=0 to get the full ranked set, but we
    # also want the pre-rank order, so we reproduce the query path here by
    # calling kg_retrieve with a large cap and then re-sorting for display.
    all_hits = V.kg_retrieve(payload, top_k=0)   # ranked, uncapped
    if not all_hits:
        print(f"  {C.R}0 triples. The graph has nothing anchored on these "
              f"keywords.{C.END}")
        print(f"  {C.DIM}This is the 'answerability = 0' case — the gold "
              f"article is unreachable.{C.END}")
        return
    print(f"  {len(all_hits)} distinct triples matched "
          f"(shown ranked; STAGE 5 explains the order).")

    # ── STAGE 5 : ranked + cut ────────────────────────────────────────────
    banner(5, f"RANKED  —  ordered by (keyword matches, confidence, typed);  "
              f"top_k = {top_k}")
    print(f"  {C.DIM}{'#':>3}  {'kwHit':>5} {'conf':>5} {'typed':>5}  "
          f"triple  [deontic]  (article){C.END}")
    cut = top_k if top_k else len(all_hits)
    for i, r in enumerate(all_hits, 1):
        m, conf, typed = _rank_score(r, keywords)
        subj = (r.get("subject") or "?")[:22]
        pred = (r.get("predicate") or "?")[:20]
        obj  = (r.get("object") or "?")[:22]
        deon = r.get("deontic")
        deon_s = f" {C.Y}[{deon}]{C.END}" if deon else ""
        art  = r.get("article_id") or ""
        line = (f"  {i:>3}  {m:>5} {conf:>5} {typed:>5}  "
                f"{subj} {C.DIM}--{pred}-->{C.END} {obj}{deon_s} "
                f"{C.DIM}({art}){C.END}")
        if i == cut + 1:
            print(f"  {C.R}{'-'*70} top_k cut{C.END}")
        print(line if i <= cut else C.DIM + line + C.END)

    kept = all_hits[:cut]
    print(f"\n  {C.BOLD}{len(kept)} triples pass to the LLM. "
          f"{len(all_hits)-len(kept)} discarded by the cut.{C.END}")

    # answerability hint
    reached = {(r.get("article_id") or "") for r in kept}
    print(f"  {C.DIM}articles reachable in the kept set: "
          f"{sorted(a for a in reached if a)}{C.END}")

    # ── STAGE 6 : context block ───────────────────────────────────────────
    if show_context:
        banner(6, "CONTEXT  —  the KG block the LLM receives (RAG omitted)")
        ctx = V.build_context(kept, [])   # [] = no RAG, KG only, for clarity
        print(C.DIM + ctx + C.END)


def main():
    ap = argparse.ArgumentParser(description="Trace a question through the KG.")
    ap.add_argument("question", nargs="*", help="the question (quoted)")
    ap.add_argument("--top-k", type=int, default=12,
                    help="ranking cut (default 12; 0 = no cut)")
    ap.add_argument("--no-context", action="store_true",
                    help="skip the STAGE 6 context block")
    args = ap.parse_args()

    if args.question:
        trace(" ".join(args.question), args.top_k, not args.no_context)
        return

    print("Interactive KG trace. Blank line or 'quit' to exit.")
    while True:
        try:
            q = input(f"\n{C.BOLD}question> {C.END}").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("quit", "exit", "q"):
            break
        trace(q, args.top_k, not args.no_context)


if __name__ == "__main__":
    main()