# verify_setup.py — preflight check before running or deploying SHIELD.
# Phase 3 aligned: checks :Concept/:REL graph schema and article-level chroma index.

import os, sys
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
CHROMA_PATH    = "./chroma_db"
COLLECTION     = "regulations"
EMBED_MODEL    = "nomic-ai/nomic-embed-text-v1.5"
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
MODEL          = "meta-llama/llama-4-scout-17b-16e-instruct"

GREEN, RED, YELLOW, DIM, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"
OK, FAIL, WARN = f"{GREEN}PASS{RESET}", f"{RED}FAIL{RESET}", f"{YELLOW}WARN{RESET}"

results = []

def record(label, status, detail=""):
    results.append((label, status, detail))
    icon = {"PASS": OK, "FAIL": FAIL, "WARN": WARN}[status]
    print(f"  [{icon}] {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))


def check_env():
    print("\nEnvironment variables")
    missing = []
    for var, val in [("GROQ_API_KEY", GROQ_API_KEY),
                     ("NEO4J_URI", NEO4J_URI),
                     ("NEO4J_USER", NEO4J_USER),
                     ("NEO4J_PASSWORD", NEO4J_PASSWORD)]:
        if val:
            shown = (val[:12] + "...") if var not in ("NEO4J_USER", "NEO4J_URI") else val
            record(var, "PASS", shown)
        else:
            record(var, "FAIL", "not set")
            missing.append(var)
    return not missing


def check_neo4j():
    print("\nNeo4j (knowledge graph — Phase 3 :Concept/:REL schema)")
    try:
        from neo4j import GraphDatabase
    except ImportError:
        record("neo4j driver installed", "FAIL", "pip install neo4j")
        return False
    if not NEO4J_PASSWORD:
        record("connection", "FAIL", "NEO4J_PASSWORD not set")
        return False
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        record("connection", "PASS", NEO4J_URI)
    except Exception as e:
        record("connection", "FAIL", str(e)[:80])
        return False

    ok = True
    try:
        def q(c):
            return driver.execute_query(c, database_=NEO4J_DATABASE).records[0][0]
        concepts = q("MATCH (n:Concept) RETURN count(n)")
        rels     = q("MATCH ()-[r:REL]->() RETURN count(r)")
        typed    = q("MATCH (n:Concept) WHERE n.typed = true RETURN count(n)")
        if concepts > 0:
            record("graph loaded", "PASS", f"{concepts} concepts, {rels} REL edges")
        else:
            record("graph loaded", "FAIL", "0 concepts — run: python graph.py")
            ok = False
        if typed > 0:
            record("typed (ontology) nodes", "PASS", f"{typed} typed concepts")
        else:
            record("typed (ontology) nodes", "WARN", "0 typed — ontology grounding missing")
    except Exception as e:
        record("graph query", "FAIL", str(e)[:80])
        ok = False
    finally:
        driver.close()
    return ok


def check_chroma():
    print("\nChromaDB (vector index — Phase 3 article-level)")
    try:
        import chromadb
    except ImportError:
        record("chromadb installed", "FAIL", "pip install chromadb")
        return False
    try:
        col = chromadb.PersistentClient(path=CHROMA_PATH).get_collection(COLLECTION)
        count = col.count()
        if count >= 50:
            record("index built", "PASS", f"{count} article chunks in '{COLLECTION}'")
            return True
        if count > 0:
            record("index built", "WARN", f"only {count} chunks — expected ~55, re-run rag.py")
            return True
        record("index built", "FAIL", "0 chunks — run: python rag.py")
        return False
    except Exception as e:
        record("index present", "FAIL", f"not found — run: python rag.py ({str(e)[:40]})")
        return False


def check_groq():
    print("\nGroq (LLM)")
    try:
        from groq import Groq
    except ImportError:
        record("groq installed", "FAIL", "pip install groq")
        return False
    if not GROQ_API_KEY:
        record("api key", "FAIL", "GROQ_API_KEY not set")
        return False
    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model=MODEL, max_tokens=5, temperature=0,
            messages=[{"role": "user", "content": "ping"}],
        )
        _ = resp.choices[0].message.content
        record("api key valid", "PASS", f"model {MODEL} reachable")
        return True
    except Exception as e:
        record("api key valid", "FAIL", str(e)[:80])
        return False


def main():
    print("=" * 60)
    print("SHIELD setup verification (Phase 3)")
    print("=" * 60)

    check_env(); check_neo4j(); check_chroma(); check_groq()

    print("\n" + "=" * 60)
    fails = sum(1 for _, s, _ in results if s == "FAIL")
    warns = sum(1 for _, s, _ in results if s == "WARN")

    if fails == 0:
        msg = "All critical checks passed"
        if warns:
            msg += f" ({warns} warning{'s' if warns > 1 else ''} — non-blocking)"
        print(f"{GREEN}{msg}. You're ready to deploy.{RESET}")
        print("=" * 60)
        sys.exit(0)
    print(f"{RED}{fails} check(s) failed. Fix the FAIL items above before deploying.{RESET}")
    print("=" * 60)
    sys.exit(1)


if __name__ == "__main__":
    main()