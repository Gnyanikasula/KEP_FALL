"""
NFR7 latency benchmark for KEP_FALL.

What this measures
-------------------
/query/stream emits a fixed sequence of SSE events (see api.py:query_stream):

    session -> step(routing) -> step(routed) -> step(retrieving)
            -> evidence -> step(synthesizing) -> verdict -> grounding
            -> reasoning_path -> done

Each event's *arrival time* at the client is a real phase boundary in the
running system, not a synthetic instrument. This script times the gaps
between them, so the reported numbers decompose end-to-end latency into:

    routing_ms        time to parse the question into intent/concepts/articles
    retrieval_ms       graph + vector retrieval (evidence event arrival)
    synthesis_ms       LLM verdict generation (verdict event arrival)
    postprocess_ms     grounding + reasoning_path + done
    total_ms           session event -> done event (full request wall time)

Why this design, for the write-up
----------------------------------
- It measures the deployed system as a user experiences it (HTTP, over the
  network, against the live Space), not a local unit-timed function call.
  That is the honest NFR figure for a "latency" requirement.
- It decomposes latency by phase without instrumenting the server, using
  only the SSE event boundaries the API already emits. This means the
  breakdown is reproducible by anyone re-running this script against the
  deployed endpoint, no server changes needed.
- It draws questions from every competency-question group (A-G) used in
  the Phase E evaluation, so latency is reported per question character
  (single-article, cross-regulation, scenario, ...), matching Table 6 of
  the dissertation rather than one arbitrary example question.

Usage
-----
    # Quick number: 5 diverse questions, 3 runs each = 15 requests total.
    python latency_bench.py --base-url https://gnyani007-kep-fall.hf.space \
        --sample 5 --runs 3 --out results

    # Full set (all 9 competency-question groups), 5 runs each = 45 requests.
    python latency_bench.py --base-url https://gnyani007-kep-fall.hf.space \
        --runs 5 --out results

    # Interrupted (Ctrl+C, connection drop, laptop slept)? Just re-run the
    # exact same command. Already-completed (question, run) pairs are read
    # back from latency_raw.csv and skipped; only what's missing is sent.

Produces:
    results/latency_raw.csv       one row per (question, run), written and
                                   flushed to disk IMMEDIATELY after each
                                   request completes — this is the
                                   checkpoint file. Safe to interrupt at
                                   any point; re-running the same command
                                   resumes instead of restarting.
    results/latency_summary.csv   mean/median/p95/p99/min/max per phase,
                                   overall and per question group
    results/latency_summary.md    the same, as a markdown table you can
                                   paste into the dissertation

Notes on interpreting the numbers
----------------------------------
- This targets a Hugging Face Spaces FREE-tier container (shared CPU, no
  GPU) and an Aura FREE Neo4j instance. Report the tier explicitly next to
  the numbers (NFR7 should state the hardware, not just the milliseconds)
  — the same code on paid infrastructure would show materially different
  synthesis_ms (the LLM call) and retrieval_ms (Aura Free throttles).
- Run with modest concurrency (default: sequential, one request at a time)
  to characterise single-user latency. For the *scalability* NFR (NFR8),
  use the companion script (concurrency_bench.py) which deliberately
  increases concurrent load and reports how these same percentiles degrade.
- The first request after a cold container start pays a one-off model-load
  tax even with Phase 0's startup warming (network + TLS handshake, and any
  provider-side cold start on the LLM API). Discard run 1 or report it
  separately as "cold" vs "warm" if you see a clear outlier — the script
  tags run_index=0 so you can filter it in analysis without re-running.
"""

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

# --------------------------------------------------------------------------
# Representative question set: mirrors Table 6 (competency-question groups)
# from the dissertation. Keep this small and fixed so every re-run is
# comparable; add questions here rather than randomising them.
# --------------------------------------------------------------------------
QUESTIONS = [
    # (group, character, question)
    ("A", "GDPR single-article",
     "What are the lawful bases for processing personal data under GDPR?"),
    ("A", "GDPR multi-article",
     "What rights does a data subject have regarding automated decisions?"),
    ("B", "EU AI Act prohibition",
     "Is it prohibited to use AI for social scoring of individuals?"),
    ("B", "EU AI Act high-risk",
     "What obligations apply to providers of high-risk AI systems?"),
    ("C", "Cross-regulation",
     "Can my diagnostic AI device store patient clinical data and share it with hospitals?"),
    ("D", "EU MDR",
     "What are the classification rules for medical devices under EU MDR 2017/745?"),
    ("E", "UK MDR",
     "What requirements apply to placing a medical device on the UK market?"),
    ("F", "DUAA",
     "What are the new safeguards for automated decision-making under the DUAA 2025?"),
    ("G", "Scenario",
     "Can my elderly-care assistant store fall-risk predictions and share them with caregivers?"),
]

PHASE_EVENTS = ["session", "evidence", "verdict", "grounding", "reasoning_path", "done"]

# Groq free-tier TPM is a ROLLING window (see engine.py's _create_with_backoff:
# RATE_LIMIT_DELAY=8s, doubling per retry -> 8s/16s/32s backoff on a 429). A
# request sent too soon after the previous one can land inside that backoff
# and measure QUEUEING time, not model latency. The clean, unthrottled
# baseline observed for this endpoint's synthesis phase is ~1-2s, so anything
# an order of magnitude above that is almost certainly a throttled/retried
# call, not a real single-shot latency sample.
THROTTLE_THRESHOLD_MS = 8000


def _iter_sse(resp: httpx.Response):
    """Yield (event_name, data_dict, t_arrival) for each SSE frame."""
    event_name = None
    for raw_line in resp.iter_lines():
        line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", "replace")
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = line.split(":", 1)[1].strip()
            t = time.perf_counter()
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {"raw": payload}
            if event_name:
                yield event_name, data, t
            event_name = None


def run_once(client: httpx.Client, base_url: str, question: str) -> dict:
    """Send one query, time every phase boundary, return a flat dict of ms."""
    t0 = time.perf_counter()
    marks = {}

    with client.stream(
        "POST", f"{base_url}/query/stream",
        json={"question": question},
        headers={"Accept": "text/event-stream"},
        timeout=httpx.Timeout(120.0, connect=10.0),
    ) as resp:
        resp.raise_for_status()
        for name, data, t in _iter_sse(resp):
            if name in PHASE_EVENTS and name not in marks:
                marks[name] = t
            if name == "error":
                marks["error"] = data.get("detail", "unknown error")
            if name == "done":
                break

    t_end = time.perf_counter()

    def ms(a, b):
        return round((b - a) * 1000, 1) if (a is not None and b is not None) else None

    session_t = marks.get("session", t0)
    evidence_t = marks.get("evidence")
    verdict_t = marks.get("verdict")
    grounding_t = marks.get("grounding")
    done_t = marks.get("done", t_end)

    return {
        "time_to_session_ms": ms(t0, session_t),
        "retrieval_ms":       ms(session_t, evidence_t),
        "synthesis_ms":       ms(evidence_t, verdict_t) if evidence_t else None,
        "postprocess_ms":     ms(verdict_t, done_t) if verdict_t else None,
        "total_ms":           ms(t0, done_t),
        "error": marks.get("error"),
    }


FIELDNAMES = ["group", "character", "run_index", "question",
              "time_to_session_ms", "retrieval_ms", "synthesis_ms",
              "postprocess_ms", "total_ms", "likely_throttled", "error"]


def _select_sample(n: int):
    """Pick n questions spread evenly across QUESTIONS (which is itself
    ordered to cover groups A-G), so a small --sample still stays diverse
    instead of just grabbing the first n (which would be all group A/B)."""
    if n >= len(QUESTIONS):
        return QUESTIONS
    if n <= 1:
        return [QUESTIONS[len(QUESTIONS) // 2]]
    step = (len(QUESTIONS) - 1) / (n - 1)
    idxs = sorted({round(i * step) for i in range(n)})
    # round() collisions can shrink the set below n; top up from the front.
    j = 0
    while len(idxs) < n:
        if j not in idxs:
            idxs.add(j)
        j += 1
    return [QUESTIONS[i] for i in sorted(idxs)][:n]


def _load_checkpoint(raw_path: Path):
    """Return the set of (question, run_index) pairs already recorded, so a
    re-run of the same command skips completed requests instead of resending
    them. Reads whatever rows are on disk; a request that errored is still
    "done" and will not be retried automatically (rerun with a fresh --out
    if you specifically want to redo failures)."""
    done = set()
    if raw_path.exists():
        with open(raw_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add((row["question"], int(row["run_index"])))
    return done


def _load_and_backfill(raw_path: Path):
    """Read latency_raw.csv, coerce numeric fields, and backfill
    likely_throttled from synthesis_ms for rows collected before that
    column existed (older runs, e.g. from before --gap/detection landed)."""
    with open(raw_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("time_to_session_ms", "retrieval_ms", "synthesis_ms",
                   "postprocess_ms", "total_ms"):
            r[k] = float(r[k]) if r.get(k) not in (None, "", "None") else None
        r["run_index"] = int(r["run_index"])
        raw_flag = r.get("likely_throttled")
        if raw_flag in (None, ""):
            syn = r.get("synthesis_ms")
            r["likely_throttled"] = bool(syn is not None and syn > THROTTLE_THRESHOLD_MS)
        else:
            r["likely_throttled"] = str(raw_flag).lower() == "true"
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True,
                     help="e.g. https://gnyani007-kep-fall.hf.space (no trailing slash)")
    ap.add_argument("--runs", type=int, default=3,
                     help="repetitions per question (default 3)")
    ap.add_argument("--sample", type=int, default=None,
                     help="use only N questions (spread across groups A-G) "
                          "instead of the full set of 9. e.g. --sample 5")
    ap.add_argument("--gap", type=float, default=65.0,
                     help="seconds to wait between requests (default 65). "
                          "Groq's free-tier TPM window is rolling; a short "
                          "gap causes later requests to land inside the "
                          "engine's rate-limit backoff and inflates "
                          "synthesis_ms with QUEUEING time, not model "
                          "latency. 65s comfortably clears a 60s window. "
                          "Use a small --gap only if you deliberately want "
                          "to reproduce/measure throttling behaviour.")
    ap.add_argument("--out", default="results", help="output directory")
    ap.add_argument("--resummarize", action="store_true",
                     help="skip sending any requests; just re-run the "
                          "all/clean summary over the existing "
                          "latency_raw.csv in --out (useful for reanalysing "
                          "data collected before --gap/throttle-detection "
                          "were added, with no new API calls)")
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "latency_raw.csv"

    if args.resummarize:
        if not raw_path.exists():
            sys.exit(f"--resummarize given but {raw_path} does not exist")
        all_rows = _load_and_backfill(raw_path)
        summarize(all_rows, out_dir)
        return

    questions = _select_sample(args.sample) if args.sample else QUESTIONS
    done = _load_checkpoint(raw_path)
    if done:
        print(f"resuming: {len(done)} request(s) already recorded in "
              f"{raw_path}, will be skipped", file=sys.stderr)

    write_header = not raw_path.exists()
    total_planned = len(questions) * args.runs
    remaining = total_planned - len(done & {
        (q, r) for _, _, q in questions for r in range(args.runs)
    })
    print(f"plan: {len(questions)} question(s) x {args.runs} run(s) "
          f"= {total_planned} total, {remaining} remaining\n", file=sys.stderr)

    i_done = 0
    with open(raw_path, "a", newline="", encoding="utf-8") as f, httpx.Client() as client:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
            f.flush()

        for group, character, question in questions:
            for run_index in range(args.runs):
                if (question, run_index) in done:
                    continue
                i_done += 1
                print(f"[{i_done}/{remaining}] group={group} run={run_index} "
                      f"q={question[:60]!r}...", file=sys.stderr)
                try:
                    result = run_once(client, base_url, question)
                except Exception as exc:
                    result = {"total_ms": None, "error": str(exc)}
                syn = result.get("synthesis_ms")
                result["likely_throttled"] = bool(
                    syn is not None and syn > THROTTLE_THRESHOLD_MS)
                if result["likely_throttled"]:
                    print(f"    -> synthesis_ms={syn:.0f} exceeds "
                          f"{THROTTLE_THRESHOLD_MS}ms: flagged likely_throttled "
                          f"(probably queued behind a Groq TPM backoff, not a "
                          f"clean sample)", file=sys.stderr)
                row = {"group": group, "character": character,
                       "run_index": run_index, "question": question, **result}
                writer.writerow(row)
                f.flush()  # checkpoint: this request can never be lost now
                time.sleep(args.gap)

    print(f"\nall requests complete, wrote {raw_path}", file=sys.stderr)
    summarize(_load_and_backfill(raw_path), out_dir)


def _pctile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (p / 100)
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def summarize(rows, out_dir: Path):
    phases = ["retrieval_ms", "synthesis_ms", "postprocess_ms", "total_ms"]
    n_throttled = sum(1 for r in rows if r.get("likely_throttled"))
    if n_throttled:
        print(f"\n{n_throttled}/{len(rows)} request(s) flagged likely_throttled "
              f"(synthesis_ms > {THROTTLE_THRESHOLD_MS}ms — almost certainly "
              f"queued behind Groq's free-tier TPM backoff, not a clean "
              f"latency sample). Reporting both 'all' and 'clean' (throttled "
              f"rows excluded) statistics below; use 'clean' for NFR7.\n",
              file=sys.stderr)

    def stats_for(subset, phase):
        vals = [r[phase] for r in subset if r.get(phase) is not None]
        if not vals:
            return None
        return {
            "n": len(vals),
            "mean": round(statistics.mean(vals), 1),
            "median": round(statistics.median(vals), 1),
            "p95": round(_pctile(vals, 95), 1),
            "p99": round(_pctile(vals, 99), 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
        }

    groups = ["OVERALL"] + sorted({r["group"] for r in rows})
    summary_rows = []
    for subset_name, subset_filter in [
        ("all", lambda rs: rs),
        ("clean", lambda rs: [r for r in rs if not r.get("likely_throttled")]),
    ]:
        for g in groups:
            base = rows if g == "OVERALL" else [r for r in rows if r["group"] == g]
            base = subset_filter(base)
            for phase in phases:
                s = stats_for(base, phase)
                if s:
                    summary_rows.append({"subset": subset_name, "group": g,
                                          "phase": phase, **s})

    csv_path = out_dir / "latency_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["subset", "group", "phase", "n", "mean",
                                           "median", "p95", "p99", "min", "max"])
        w.writeheader()
        w.writerows(summary_rows)
    print(f"wrote {csv_path}", file=sys.stderr)

    md_path = out_dir / "latency_summary.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("| Subset | Group | Phase | n | Mean (ms) | Median (ms) | p95 (ms) | p99 (ms) | Min | Max |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for r in summary_rows:
            f.write(f"| {r['subset']} | {r['group']} | {r['phase']} | {r['n']} | "
                     f"{r['mean']} | {r['median']} | {r['p95']} | {r['p99']} | "
                     f"{r['min']} | {r['max']} |\n")
    print(f"wrote {md_path}", file=sys.stderr)

    for subset_name in ("all", "clean"):
        overall_total = [r for r in summary_rows if r["subset"] == subset_name
                          and r["group"] == "OVERALL" and r["phase"] == "total_ms"]
        if overall_total:
            s = overall_total[0]
            label = "ALL requests (includes any throttled)" if subset_name == "all" \
                else "CLEAN requests only (throttled rows excluded — use this for NFR7)"
            print(f"{label}: n={s['n']}  median={s['median']}ms  "
                  f"p95={s['p95']}ms  p99={s['p99']}ms", file=sys.stderr)
    print("", file=sys.stderr)


if __name__ == "__main__":
    main()