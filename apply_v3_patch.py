"""
apply_v3_patch2.py — SHIELD gny_v3 migration (robust call-site rewrite)

Replaces apply_v3_patch.py. Same intent, but the two LLM call sites are now
rewritten STRUCTURALLY (by locating the call and balancing parentheses) rather
than by exact string match, so it works whether or not reasoning_effort or any
other keyword has already been added by hand.

Design rules (unchanged):
  * The retrieved chunk SET is not altered. Gold recall stays 0.872, identical
    to the frozen gny_v2 baseline. Only per-chunk excerpt depth is budgeted.
  * Applied identically to every RAG-bearing arm, so hybrid vs rag_only stays
    a fair comparison when the evaluation is re-run later.
  * kg_only / kg_typed_only / kg_untyped_only are untouched.

Run from the repo root on branch gny_v3:
    python apply_v3_patch2.py --check
    python apply_v3_patch2.py
"""
import argparse
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OLD_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
NEW_MODEL = "openai/gpt-oss-120b"


# ---------------------------------------------------------------- utilities

def match_paren(text, open_idx):
    """Return index just past the ')' matching the '(' at open_idx.

    String-aware so a parenthesis inside a literal does not confuse the count.
    """
    depth = 0
    i = open_idx
    quote = None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if text.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if text.startswith(('"""', "'''"), i):
            quote = text[i:i + 3]
            i += 3
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced parentheses")


def function_span(text, name):
    """Return (start, end) character span of a top-level `def name(`."""
    m = re.search(rf"^def {re.escape(name)}\(", text, re.M)
    if not m:
        return None
    start = m.start()
    nxt = re.search(r"^(def |# ---|class )", text[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    return start, end


def line_indent(text, idx):
    """Leading whitespace of the line containing idx.

    Must not include code such as `resp = ` that precedes the call on the
    same line, or the rewritten call is emitted at the wrong indentation.
    """
    ls = text.rfind("\n", 0, idx) + 1
    return re.match(r"[ \t]*", text[ls:idx]).group(0)


# ------------------------------------------------------- verdict.py inserts

V_CONSTS_OLD = """MAX_RETRIES    = 2
RETRY_DELAY    = 2"""

V_CONSTS_NEW = '''MAX_RETRIES    = 2
RETRY_DELAY    = 2

# --- Free-tier token budget (gny_v3) ------------------------------------
# openai/gpt-oss-120b free tier: 30 RPM, 8,000 TPM, 200,000 TPD.
# The whole retrieved chunk SET is kept (recall unchanged vs the gny_v2
# baseline); only per-chunk excerpt depth is tiered. The RAG_HEAD_N chunks
# with the smallest embedding distance keep RAG_HEAD_CHARS characters, the
# remainder keep RAG_TAIL_CHARS. Measured: mean ~5.8K, max ~6.7K tokens per
# call including output, leaving headroom for reasoning tokens.
RAG_HEAD_N     = int(os.getenv("SHIELD_RAG_HEAD_N", "8"))
RAG_HEAD_CHARS = int(os.getenv("SHIELD_RAG_HEAD_CHARS", "1200"))
RAG_TAIL_CHARS = int(os.getenv("SHIELD_RAG_TAIL_CHARS", "400"))

# Reasoning tokens count towards TPM, so cap them and cap the completion.
REASONING_EFFORT      = os.getenv("SHIELD_REASONING_EFFORT", "low")
MAX_COMPLETION_TOKENS = int(os.getenv("SHIELD_MAX_COMPLETION", "1200"))

# 429 / rate-limit backoff. TPM is a rolling window, so waiting genuinely
# clears it — unlike a malformed-JSON error, which needs a re-prompt.
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_DELAY   = 8'''

V_BACKOFF_ANCHOR = """# Lazy singletons
_DRIVER         = None"""

V_BACKOFF_NEW = '''def _create_with_backoff(client, **kwargs):
    """Groq chat completion with rate-limit backoff.

    Free-tier TPM is 8,000 and is shared across the whole organisation, so
    two concurrent demo users can trip a 429 even though nothing is wrong.
    A rate-limit error is transient and worth waiting out; anything else is
    re-raised immediately.
    """
    delay = RATE_LIMIT_DELAY
    for attempt in range(1 + RATE_LIMIT_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as err:
            msg = str(err).lower()
            transient = ("rate_limit" in msg or "429" in msg
                         or "too large" in msg or "413" in msg)
            if not transient or attempt == RATE_LIMIT_RETRIES:
                raise
            print(f"[rate-limit] attempt {attempt + 1}, waiting {delay}s")
            time.sleep(delay)
            delay *= 2


# Lazy singletons
_DRIVER         = None'''

V_RAGRET_OLD = '''    out, seen = [], set()
    for q in queries:
        res = col.query(query_embeddings=[_embed(q)], n_results=k)
        for cid, doc, meta in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0]
        ):
            if cid not in seen:
                seen.add(cid)
                out.append({
                    "chunk_id": cid,
                    "citation": meta.get("citation", cid),
                    "text":     doc,
                    "type":     meta.get("type", ""),
                })
    return out'''

V_RAGRET_NEW = '''    # Distances were previously discarded. They are kept now so build_context()
    # can allocate excerpt depth by relevance. The retrieved SET is unchanged.
    out, seen = [], {}
    for q in queries:
        res = col.query(query_embeddings=[_embed(q)], n_results=k)
        dists = (res.get("distances") or [[None] * len(res["ids"][0])])[0]
        for cid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], dists
        ):
            if cid in seen:
                prev = seen[cid]["distance"]
                if dist is not None and (prev is None or dist < prev):
                    seen[cid]["distance"] = dist
                continue
            rec = {
                "chunk_id": cid,
                "citation": meta.get("citation", cid),
                "text":     doc,
                "type":     meta.get("type", ""),
                "distance": dist,
            }
            seen[cid] = rec
            out.append(rec)
    return out'''

V_RAGKNOW_OLD = '''    out, seen = [], set()
    for query in queries:
        res = col.query(query_embeddings=[_embed(query)], n_results=k)
        for cid, doc, meta in zip(res["ids"][0], res["documents"][0], res["metadatas"][0]):
            if cid not in seen:
                seen.add(cid)
                out.append({"chunk_id": cid,
                            "citation": meta.get("citation", cid),
                            "text": doc,
                            "type": meta.get("type", "")})
    return out'''

V_RAGKNOW_NEW = '''    out, seen = [], {}
    for query in queries:
        res = col.query(query_embeddings=[_embed(query)], n_results=k)
        dists = (res.get("distances") or [[None] * len(res["ids"][0])])[0]
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                        res["metadatas"][0], dists):
            if cid in seen:
                prev = seen[cid]["distance"]
                if dist is not None and (prev is None or dist < prev):
                    seen[cid]["distance"] = dist
                continue
            rec = {"chunk_id": cid,
                   "citation": meta.get("citation", cid),
                   "text": doc,
                   "type": meta.get("type", ""),
                   "distance": dist}
            seen[cid] = rec
            out.append(rec)
    return out'''

V_CONTEXT_OLD = '''    lines.append("\\n## REGULATION EXCERPTS (verbatim, for grounding)")
    for c in rag:
        excerpt = c["text"][:3000].replace("\\n", " ")
        lines.append(f"### {c['citation']}\\n{excerpt}")
    return "\\n".join(lines)'''

V_CONTEXT_NEW = '''    lines.append("\\n## REGULATION EXCERPTS (verbatim, for grounding)")
    # Tiered excerpt depth. Every retrieved chunk is still emitted with its
    # citation header, so the retrieved SET — and therefore faithful-F1,
    # hallucination and answerability — is unchanged from the gny_v2 baseline.
    # Only the amount of text per chunk is budgeted, by embedding distance.
    ranked = sorted(
        range(len(rag)),
        key=lambda i: (rag[i].get("distance") is None,
                       rag[i].get("distance") if rag[i].get("distance") is not None else 0.0),
    )
    head = set(ranked[:RAG_HEAD_N])
    for i, c in enumerate(rag):
        limit = RAG_HEAD_CHARS if i in head else RAG_TAIL_CHARS
        raw = c["text"]
        excerpt = raw[:limit].replace("\\n", " ")
        # Mark truncation explicitly so the model does not treat a cut excerpt
        # as the complete provision when reasoning about it.
        if len(raw) > limit:
            excerpt += " [... excerpt truncated ...]"
        lines.append(f"### {c['citation']}\\n{excerpt}")
    return "\\n".join(lines)'''

R_CONSTS_OLD = 'MODEL        = "meta-llama/llama-4-scout-17b-16e-instruct"'

R_CONSTS_NEW = '''MODEL        = "openai/gpt-oss-120b"

# Reasoning tokens count towards the free-tier TPM window, so keep the routing
# call — which runs on every request — as cheap as possible.
REASONING_EFFORT      = os.getenv("SHIELD_REASONING_EFFORT", "low")
MAX_COMPLETION_TOKENS = int(os.getenv("SHIELD_ROUTE_MAX_COMPLETION", "400"))
RATE_LIMIT_RETRIES    = 3
RATE_LIMIT_DELAY      = 8'''

R_CALL_NEW = '''def call_llm(question: str, nudge: str = "") -> str:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    delay = RATE_LIMIT_DELAY
    for attempt in range(1 + RATE_LIMIT_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=0,
                reasoning_effort=REASONING_EFFORT,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM + nudge},
                          {"role": "user",   "content": question}],
            )
            return resp.choices[0].message.content
        except Exception as err:
            msg = str(err).lower()
            transient = ("rate_limit" in msg or "429" in msg
                         or "too large" in msg or "413" in msg)
            if not transient or attempt == RATE_LIMIT_RETRIES:
                raise
            print(f"[rate-limit:route] attempt {attempt + 1}, waiting {delay}s")
            time.sleep(delay)
            delay *= 2

'''


# ----------------------------------------------------- structural rewrites

def rewrite_synthesize(text, log):
    """Point _synthesize's Groq call at _create_with_backoff, whatever kwargs
    are currently present."""
    span = function_span(text, "_synthesize")
    if not span:
        return text, "verdict.py: _synthesize() not found"
    s, e = span
    body = text[s:e]
    if "_create_with_backoff(" in body:
        log.append("verdict.py: [_synthesize] already uses backoff, skipping")
        return text, None

    m = re.search(r"client\.chat\.completions\.create\s*\(", body)
    if not m:
        return text, "verdict.py: no create() call inside _synthesize()"
    open_idx = body.index("(", m.start())
    end = match_paren(body, open_idx)
    indent = line_indent(body, m.start())

    new_call = (
        "_create_with_backoff(\n"
        f"{indent}    client,\n"
        f"{indent}    model=MODEL, temperature=0,\n"
        f"{indent}    reasoning_effort=REASONING_EFFORT,\n"
        f"{indent}    max_completion_tokens=MAX_COMPLETION_TOKENS,\n"
        f'{indent}    response_format={{"type": "json_object"}},\n'
        f"{indent}    messages=messages,\n"
        f"{indent})"
    )
    body = body[:m.start()] + new_call + body[end:]
    log.append("verdict.py: [_synthesize] rewritten to use backoff")
    return text[:s] + body + text[e:], None


def rewrite_call_llm(text, log):
    """Replace route.py's call_llm() wholesale with the backoff version."""
    span = function_span(text, "call_llm")
    if not span:
        return text, "route.py: call_llm() not found"
    s, e = span
    if "RATE_LIMIT_RETRIES" in text[s:e]:
        log.append("route.py: [call_llm] already has backoff, skipping")
        return text, None
    log.append("route.py: [call_llm] replaced with backoff version")
    return text[:s] + R_CALL_NEW + text[e:], None


# ------------------------------------------------------------------ driver

EXACT = {
    "verdict.py": [
        ("model id", f'MODEL          = "{OLD_MODEL}"',
         f'MODEL          = "{NEW_MODEL}"'),
        ("budget constants", V_CONSTS_OLD, V_CONSTS_NEW, "RAG_HEAD_N"),
        ("backoff helper", V_BACKOFF_ANCHOR, V_BACKOFF_NEW,
         "def _create_with_backoff"),
        ("rag_retrieve distances", V_RAGRET_OLD, V_RAGRET_NEW),
        ("rag_knowledge distances", V_RAGKNOW_OLD, V_RAGKNOW_NEW),
        ("tiered build_context", V_CONTEXT_OLD, V_CONTEXT_NEW),
    ],
    "route.py": [
        ("model id + constants", R_CONSTS_OLD, R_CONSTS_NEW),
    ],
    "verify_setup.py": [
        ("model id", f'MODEL          = "{OLD_MODEL}"',
         f'MODEL          = "{NEW_MODEL}"'),
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    plan, problems, log = {}, [], []

    for path, edits in EXACT.items():
        if not os.path.exists(path):
            problems.append(f"{path}: not found (run from repo root)")
            continue
        text = original = open(path, encoding="utf-8").read()

        for edit in edits:
            label, old, new = edit[0], edit[1], edit[2]
            guard = edit[3] if len(edit) > 3 else None
            if guard and guard in text:
                log.append(f"{path}: [{label}] already applied, skipping")
                continue
            n = text.count(old)
            if n == 1:
                text = text.replace(old, new, 1)
                log.append(f"{path}: [{label}] ok")
            elif n == 0:
                if new.split("\n")[0] in text:
                    log.append(f"{path}: [{label}] already applied, skipping")
                else:
                    problems.append(f"{path}: [{label}] snippet not found")
            else:
                problems.append(f"{path}: [{label}] appears {n}x, not unique")

        if path == "verdict.py":
            text, err = rewrite_synthesize(text, log)
            if err:
                problems.append(err)
        if path == "route.py":
            text, err = rewrite_call_llm(text, log)
            if err:
                problems.append(err)
            if "\nimport time" not in text and not text.startswith("import time"):
                if "import json" in text:
                    text = text.replace("import json", "import json, time", 1)
                    log.append("route.py: [import time] added")

        if text != original:
            plan[path] = text

    for line in log:
        print(line)

    if problems:
        print("\nABORTED — no files written:")
        for p in problems:
            print("  " + p)
        return 1

    if args.check:
        print(f"\nDry run OK. {len(plan)} file(s) would change.")
        return 0

    for path, text in plan.items():
        open(path, "w", encoding="utf-8").write(text)
        print(f"WROTE {path}")

    print("\nDone. Next:")
    print("  python verify_setup.py")
    print("  uvicorn api:app --host 0.0.0.0 --port 7860")
    return 0


if __name__ == "__main__":
    sys.exit(main())