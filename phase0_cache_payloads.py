"""
phase0_cache_payloads.py

Routes each of the 65 evaluation questions ONCE and saves the resulting
QueryPayload to disk. Every later retrieval sweep and audit then reuses these
cached payloads and costs zero API calls.

Why this exists:
  route.py SYSTEM is ~2,750 tokens. At 65 questions that is ~188K tokens -
  roughly a full day of gpt-oss-120b free-tier TPD (200K). Paying it once and
  reusing it is the difference between a feasible tuning loop and an
  impossible one.

This is the ONLY Phase 0 script that calls the API.

Run:  python phase0_cache_payloads.py
      python phase0_cache_payloads.py --resume     (skip already-cached)
Out:  phase0_out/payloads.json
"""
import argparse
import json
import os
import sys
import time

OUT_DIR = "phase0_out"
OUT_PATH = os.path.join(OUT_DIR, "payloads.json")
QUESTIONS = "eval_questions_full.json"

# Free-tier pacing. route calls are ~2.9K tokens each. At 8K TPM
# (gpt-oss-120b) that is roughly 2 calls/minute before throttling.
SLEEP_BETWEEN = 30.0

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true",
                    help="keep existing cached payloads, only fill gaps")
    ap.add_argument("--sleep", type=float, default=SLEEP_BETWEEN,
                    help="seconds between calls (free-tier TPM pacing)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process first N questions (smoke test)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    from route import understand_query

    questions = json.load(open(QUESTIONS, encoding="utf-8"))
    if args.limit:
        questions = questions[:args.limit]

    cache = {}
    if args.resume and os.path.exists(OUT_PATH):
        cache = json.load(open(OUT_PATH, encoding="utf-8"))
        print(f"Resuming: {len(cache)} payloads already cached")

    todo = [q for q in questions if q["cq_id"] not in cache]
    print(f"To route: {len(todo)} / {len(questions)} questions")
    print(f"Pacing: {args.sleep}s between calls "
          f"(~{len(todo) * args.sleep / 60:.0f} min total)\n")

    failures = []
    for i, cq in enumerate(todo, 1):
        cqid = cq["cq_id"]
        try:
            payload = understand_query(cq["question"])
            if payload is None:
                failures.append((cqid, "router returned None"))
                print(f"[{i}/{len(todo)}] {cqid}  FAILED (None)")
            else:
                cache[cqid] = payload.model_dump()
                print(f"[{i}/{len(todo)}] {cqid}  intent={payload.intent}")
        except Exception as e:
            failures.append((cqid, f"{type(e).__name__}: {str(e)[:120]}"))
            print(f"[{i}/{len(todo)}] {cqid}  ERROR {type(e).__name__}: "
                  f"{str(e)[:120]}")
            # Rate-limit errors need a longer pause before continuing.
            if "rate_limit" in str(e).lower() or "429" in str(e):
                print("     rate limited - sleeping 65s")
                time.sleep(65)

        # Save after every call so a crash never loses progress.
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)

        if i < len(todo):
            time.sleep(args.sleep)

    print(f"\nCached {len(cache)} payloads -> {OUT_PATH}")
    if failures:
        print(f"\n{len(failures)} failures (re-run with --resume to retry):")
        for cqid, err in failures:
            print(f"  {cqid}: {err}")


if __name__ == "__main__":
    main()