"""
NFR8 scalability benchmark for KEP_FALL.

What "scalability" means for this system, and why it's tested this way
------------------------------------------------------------------------
This system has no autoscaling: it is one FastAPI container on a Hugging
Face Spaces FREE tier (single shared vCPU) talking to one Neo4j Aura FREE
instance (capped connection pool) and one on-disk Chroma index. There is
no cluster to add nodes to. So "scalability" cannot honestly be reported
as "throughput under horizontal scale-out" (Anthropic and most SaaS-style
NFR templates assume that; this deployment does not have it).

What CAN be honestly measured, and what this script measures, is:
    capacity  - how many concurrent users the CURRENT single instance
                 sustains before latency or the error rate become
                 unacceptable.
    degradation - how gracefully (or not) latency grows as concurrent
                 load increases, i.e. is the curve linear (predictable,
                 addressable by adding replicas) or does it fall off a
                 cliff (a hard bottleneck, e.g. the Neo4j connection pool
                 or a single-worker Uvicorn process serializing requests).

This is the correct NFR8 evidence for a dissertation: it characterises the
CURRENT deployment honestly, and the architectural discussion (stateless
API, swappable Neo4j/Chroma backends) argues SEPARATELY, as a design
property rather than a measured one, that the architecture would scale
horizontally given paid infrastructure. Do not conflate the two in the
writeup: report the measured ceiling of THIS deployment, then argue the
architectural headroom qualitatively.

Method
------
For each concurrency level in --levels (default: 1,2,4,8), fire that many
requests at /query/stream simultaneously (asyncio, one task per request),
wait for all to finish, record each request's total latency and whether it
errored or timed out, then move to the next level. A short cooldown between
levels lets the free-tier container recover so levels don't contaminate
each other.

Usage
-----
    python concurrency_bench.py --base-url https://gnyani007-kep-fall.hf.space \
        --levels 1,2,4,8 --per-level 4 --out results

Produces:
    results/concurrency_raw.csv       one row per request
    results/concurrency_summary.csv   p50/p95/error-rate per concurrency level
    results/concurrency_summary.md    the same, as a markdown table

Caution
-------
This deliberately loads a live, free-tier, shared service. Keep --levels
modest (this project's default tops out at 8 concurrent requests) and run
it once, not repeatedly — a free Aura instance and a free HF Space are
shared/throttled resources, and hammering them does not produce more valid
data, just a worse one-off result and a risk of tripping rate limits.
"""

import argparse
import asyncio
import csv
import statistics
import sys
import time
from pathlib import Path

import httpx

QUESTION = "Can my diagnostic AI device store patient clinical data and share it with hospitals?"


async def one_request(client: httpx.AsyncClient, base_url: str, level: int, idx: int) -> dict:
    t0 = time.perf_counter()
    try:
        async with client.stream(
            "POST", f"{base_url}/query/stream",
            json={"question": QUESTION},
            headers={"Accept": "text/event-stream"},
            timeout=httpx.Timeout(120.0, connect=10.0),
        ) as resp:
            status = resp.status_code
            async for _ in resp.aiter_lines():
                pass  # drain the stream to completion
        t1 = time.perf_counter()
        return {"level": level, "idx": idx, "total_ms": round((t1 - t0) * 1000, 1),
                "status": status, "error": None}
    except Exception as exc:
        t1 = time.perf_counter()
        return {"level": level, "idx": idx, "total_ms": round((t1 - t0) * 1000, 1),
                "status": None, "error": str(exc)[:200]}


async def run_level(base_url: str, level: int, per_level: int) -> list[dict]:
    async with httpx.AsyncClient() as client:
        tasks = [one_request(client, base_url, level, i)
                 for i in range(level * per_level)]
        return await asyncio.gather(*tasks)


def _pctile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (p / 100)
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    return values[f] if f == c else values[f] + (values[c] - values[f]) * (k - f)


async def main_async(args):
    levels = [int(x) for x in args.levels.split(",")]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for level in levels:
        print(f"=== concurrency level {level} "
              f"({level * args.per_level} requests fired at once) ===", file=sys.stderr)
        rows = await run_level(args.base_url.rstrip("/"), level, args.per_level)
        all_rows.extend(rows)
        n_err = sum(1 for r in rows if r["error"])
        print(f"    -> {len(rows)} requests, {n_err} errors", file=sys.stderr)
        if level != levels[-1]:
            print(f"    cooling down {args.cooldown}s before next level...", file=sys.stderr)
            await asyncio.sleep(args.cooldown)

    raw_path = out_dir / "concurrency_raw.csv"
    with open(raw_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["level", "idx", "total_ms", "status", "error"])
        w.writeheader()
        w.writerows(all_rows)
    print(f"wrote {raw_path}", file=sys.stderr)

    summary_rows = []
    for level in levels:
        subset = [r for r in all_rows if r["level"] == level]
        ok = [r["total_ms"] for r in subset if not r["error"]]
        n_err = sum(1 for r in subset if r["error"])
        summary_rows.append({
            "concurrency": level,
            "requests": len(subset),
            "errors": n_err,
            "error_rate": round(n_err / len(subset), 3) if subset else None,
            "p50_ms": round(statistics.median(ok), 1) if ok else None,
            "p95_ms": round(_pctile(ok, 95), 1) if ok else None,
            "max_ms": round(max(ok), 1) if ok else None,
        })

    csv_path = out_dir / "concurrency_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["concurrency", "requests", "errors", "error_rate",
                                           "p50_ms", "p95_ms", "max_ms"])
        w.writeheader()
        w.writerows(summary_rows)
    print(f"wrote {csv_path}", file=sys.stderr)

    md_path = out_dir / "concurrency_summary.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("| Concurrency | Requests | Errors | Error rate | p50 (ms) | p95 (ms) | Max (ms) |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in summary_rows:
            f.write(f"| {r['concurrency']} | {r['requests']} | {r['errors']} | "
                     f"{r['error_rate']} | {r['p50_ms']} | {r['p95_ms']} | {r['max_ms']} |\n")
    print(f"wrote {md_path}", file=sys.stderr)

    print("\nLook for: (a) the concurrency level where error_rate first becomes "
          "non-zero (that's your current capacity ceiling), and (b) whether p95 "
          "grows roughly linearly with concurrency (predictable degradation) or "
          "jumps sharply at one level (a hard bottleneck, e.g. connection-pool "
          "exhaustion). Report both in NFR8.\n", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--levels", default="1,2,4,8",
                     help="comma-separated concurrency levels to test")
    ap.add_argument("--per-level", type=int, default=2,
                     help="requests PER concurrent slot at each level "
                          "(total fired = level * per_level)")
    ap.add_argument("--cooldown", type=float, default=15.0,
                     help="seconds to rest between levels")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()