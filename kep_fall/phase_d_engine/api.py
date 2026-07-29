import json, logging, os, sys, time, uuid, asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import chromadb
from neo4j import GraphDatabase

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from kep_fall.phase_d_engine import engine as V
from kep_fall.phase_d_engine.router import understand_query
from kep_fall.phase_d_engine.history import SQLiteHistoryStore
from kep_fall import config


# logging
class JsonFormatter(logging.Formatter):
    RESERVED = {"name","msg","args","levelname","levelno","pathname","filename",
                "module","exc_info","exc_text","stack_info","lineno","funcName",
                "created","msecs","relativeCreated","thread","threadName",
                "processName","process","taskName"}
    def format(self, r):
        p = {"ts": datetime.now(timezone.utc).isoformat(), "level": r.levelname,
             "logger": r.name, "msg": r.getMessage()}
        for k, v in r.__dict__.items():
            if k not in self.RESERVED and not k.startswith("_"):
                p[k] = v
        if r.exc_info:
            p["exc"] = self.formatException(r.exc_info)
        return json.dumps(p, default=str)

_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(JsonFormatter())
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[_h], force=True)
for noisy in ("httpx", "neo4j", "urllib3", "chromadb", "sentence_transformers"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("shield")

# HISTORY_DB = os.getenv("HISTORY_DB_PATH", "data/shield_history.db")
HISTORY_DB = config.HISTORY_DB
store = SQLiteHistoryStore(HISTORY_DB)


# models
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None

class QueryResponse(BaseModel):
    session_id: str
    question:   str
    verdict:    str
    rules:      list[str]
    reasoning:  str
    conditions: list[str] = []
    confidence: int
    parsed:     dict
    request_id: str

class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str

class CreateSession(BaseModel):
    title: str = "New session"

class Feedback(BaseModel):
    session_id: str
    question:   str
    verdict:    str
    rating:     int
    notes:      str = ""


# chroma bootstrap (Phase 3 aligned)
def ensure_chroma_index() -> None:
    """Verify the Phase 3 article-level index exists. Does NOT rebuild — the
    index is built by rag.py and shipped in ./chroma_db. If missing, log a
    clear error so the operator runs rag.py rather than silently degrading."""
    try:
        col = chromadb.PersistentClient(path=V.CHROMA_PATH).get_collection(V.COLLECTION)
        n = col.count()
        if n > 0:
            log.info("chroma index present", extra={"count": n})
            return
        log.error("chroma collection empty — run: python rag.py")
    except Exception as e:
        log.error("chroma index missing — run: python rag.py",
                  extra={"error": str(e)[:120]})


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("KEP_FALL starting")
    ensure_chroma_index()
    log.info("KEP_FALL ready")
    yield
    log.info("KEP_FALL stopped")

app = FastAPI(title="KEP_FALL API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"],
)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid
    start = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Request-ID"] = rid
    log.info("request", extra={"request_id": rid, "method": request.method,
             "path": request.url.path, "status": resp.status_code,
             "ms": round((time.perf_counter()-start)*1000, 1)})
    return resp


# health
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/health/deep")
def health_deep():
    checks = {"chroma": "unknown", "neo4j": "unknown"}
    try:
        n = chromadb.PersistentClient(path=V.CHROMA_PATH).get_collection(V.COLLECTION).count()
        checks["chroma"] = f"ok ({n} chunks)"
    except Exception as e:
        checks["chroma"] = f"error: {e}"
    try:
        d = GraphDatabase.driver(V.NEO4J_URI, auth=(V.NEO4J_USER, V.NEO4J_PASSWORD))
        d.verify_connectivity(); d.close()
        checks["neo4j"] = "ok"
    except Exception as e:
        checks["neo4j"] = f"error: {e}"
    ok = all(v.startswith("ok") for v in checks.values())
    return {"status": "ok" if ok else "degraded", "checks": checks}


# sessions
@app.post("/sessions", response_model=SessionSummary, status_code=201)
def create_session(req: CreateSession):
    return store.create_session(req.title)

@app.get("/sessions", response_model=list[SessionSummary])
def list_sessions():
    return store.list_sessions()

@app.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    if not store.session_exists(session_id):
        raise HTTPException(404, "Session not found")
    store.delete_session(session_id)

@app.get("/sessions/{session_id}/history")
def get_history(session_id: str):
    if not store.session_exists(session_id):
        raise HTTPException(404, "Session not found")
    return {"session_id": session_id, "messages": store.get_messages(session_id)}


# shared query core
def _resolve_session(req: QueryRequest) -> str:
    if req.session_id and store.session_exists(req.session_id):
        return req.session_id
    title = (req.question[:60] + "...") if len(req.question) > 60 else req.question
    return store.create_session(title)["id"]


def _run_pipeline(question: str, sid: str) -> tuple:
    """Run the full pipeline. Returns (result, parsed_dict).

    Uses analyze_full so routing happens ONCE. The previous version called
    analyze_with_history (which routes internally, with history) and then
    understand_query(question) again (without history) just to get `parsed` —
    two routes per query, and the displayed payload could differ from the one
    retrieval actually used. `plan.payload` is the exact payload the pipeline
    ran on, so `parsed` is now guaranteed consistent with the verdict.
    """
    history = store.get_messages(sid)
    plan, _evidence, result = V.analyze_full(question, history)
    parsed = plan.payload.model_dump() if plan else {}
    return result, parsed


def _persist(sid: str, result, parsed: dict) -> None:
    store.add_message(sid, "assistant", result.verdict, verdict={
        "verdict": result.verdict, "rules": result.rules,
        "reasoning": result.reasoning, "conditions": result.conditions,
        "confidence": result.confidence, "payload": parsed,
    })


def _verdict_frame(sid: str, question: str, result, parsed: dict,
                   rid: str) -> dict:
    """The verdict payload sent to the client, shared by the blocking and
    streaming endpoints so their shapes can't drift."""
    return {
        "session_id": sid, "question": question,
        "verdict": result.verdict, "rules": result.rules,
        "reasoning": result.reasoning, "conditions": result.conditions,
        "confidence": result.confidence, "parsed": parsed, "request_id": rid,
    }


# blocking query
@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, request: Request):
    rid = request.state.request_id
    sid = _resolve_session(req)
    store.add_message(sid, "user", req.question)
    log.info("query", extra={"request_id": rid, "session_id": sid})

    result, parsed = _run_pipeline(req.question, sid)
    if not result:
        raise HTTPException(502, "Verdict synthesis failed.")

    log.info("verdict", extra={"request_id": rid, "verdict": result.verdict,
             "confidence": result.confidence})
    _persist(sid, result, parsed)

    return QueryResponse(
        session_id=sid, question=req.question,
        verdict=result.verdict, rules=result.rules, reasoning=result.reasoning,
        conditions=result.conditions, confidence=result.confidence,
        parsed=parsed, request_id=rid,
    )


# streaming query (SSE) 
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

@app.post("/query/stream")
async def query_stream(req: QueryRequest, request: Request):
    rid = request.state.request_id
    sid = _resolve_session(req)
    store.add_message(sid, "user", req.question)
    log.info("query_stream", extra={"request_id": rid, "session_id": sid})

    async def gen():
        # Some proxies and browsers buffer a streamed response until ~2KB has
        # accumulated, which holds the early `step` frames back until the
        # verdict arrives — the steps then flash past in a single tick and the
        # user sees nothing but an empty panel. A one-off padding comment
        # (SSE lines beginning ':' are ignored by the client) fills that buffer
        # immediately so every subsequent frame flushes as soon as it is sent.
        yield ":" + (" " * 2048) + "\n\n"
        yield _sse("session", {"session_id": sid})
        yield _sse("step", {"stage": "routing", "label": "Understanding the question"})
        await asyncio.sleep(0.05)

        loop = asyncio.get_event_loop()

        # --- Stage 1: prepare (routes ONCE) ------------------------------
        # Any exception here (e.g. an LLM API 400/timeout) must be surfaced to
        # the client as an `error` event; letting it propagate kills the
        # generator mid-flight and the browser sees the connection close with
        # no verdict and no error — the "stays blank then nothing" symptom.
        try:
            history = store.get_messages(sid)
            plan = await loop.run_in_executor(None, V.prepare, req.question, history)
        except Exception as exc:
            log.error("route_failed", extra={"request_id": rid}, exc_info=exc)
            yield _sse("error", {"detail": "Could not understand the question. "
                                           "Please try rephrasing.", "request_id": rid})
            return
        if plan is None:
            yield _sse("error", {"detail": "Could not understand the question."})
            return

        parsed = plan.payload.model_dump()
        yield _sse("step", {"stage": "routed",
                            "label": f"Intent: {plan.intent}",
                            "intent": plan.intent,
                            "jurisdiction": plan.payload.jurisdiction})
        await asyncio.sleep(0.05)

        # --- Canned intents: no retrieval, no synthesis ------------------
        if plan.mode == "canned":
            result = plan.canned
            _persist(sid, result, parsed)
            yield _sse("verdict", _verdict_frame(sid, req.question, result, parsed, rid))
            yield _sse("done", {"ok": True})
            return

        # --- Stage 2: retrieve, then emit the evidence BEFORE synthesis --
        # This is the honest ordering: the graph edges and passages exist the
        # moment retrieval returns, before the LLM has written a word. Emitting
        # them here populates the provenance panel while synthesis runs, rather
        # than after.
        stage_label = ("Retrieving regulations"
                       if plan.intent in ("knowledge", "scenario")
                       else "Preparing response")
        yield _sse("step", {"stage": "retrieving", "label": stage_label})
        try:
            evidence = await loop.run_in_executor(None, V.retrieve, plan)
        except Exception as exc:
            log.error("retrieve_failed", extra={"request_id": rid}, exc_info=exc)
            yield _sse("error", {"detail": "Failed to retrieve regulatory context. "
                                           "Please try again.", "request_id": rid})
            return

        summary = V.evidence_summary(evidence)
        log.info("evidence", extra={"request_id": rid,
                 "kg_edges": summary["counts"]["edges"],
                 "rag_passages": summary["counts"]["passages"]})
        yield _sse("evidence", {"session_id": sid, "request_id": rid, **summary})
        await asyncio.sleep(0.05)

        # --- Stage 3: synthesize -----------------------------------------
        yield _sse("step", {"stage": "synthesizing", "label": "Synthesizing verdict"})
        try:
            result = await loop.run_in_executor(None, V.synthesize, plan, evidence)
        except Exception as exc:
            log.error("synthesis_failed", extra={"request_id": rid}, exc_info=exc)
            yield _sse("error", {"detail": "Verdict synthesis failed. Please try again.",
                                 "request_id": rid})
            return
        if not result:
            yield _sse("error", {"detail": "Verdict synthesis failed."})
            return

        _persist(sid, result, parsed)
        log.info("verdict", extra={"request_id": rid, "verdict": result.verdict})

        # Deterministic grounding: which cited articles are backed by the
        # retrieved evidence (graph edge / corpus passage / neither).
        grounding = V.ground_citations(result, evidence)
        log.info("grounding", extra={"request_id": rid, **grounding["counts"]})

        # Reasoning path for the provenance diagram: grounded citations traced
        # back to the graph edges that support them.
        rpath = V.reasoning_path(result, evidence, grounding)

        yield _sse("verdict", _verdict_frame(sid, req.question, result, parsed, rid))
        yield _sse("grounding", {"session_id": sid, "request_id": rid, **grounding})
        yield _sse("reasoning_path", {"session_id": sid, "request_id": rid, **rpath})
        yield _sse("done", {"ok": True})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Request-ID": rid,
                                      "Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# feedback
@app.post("/feedback")
def feedback(fb: Feedback):
    store.add_feedback(fb.session_id, fb.question, fb.verdict, fb.rating, fb.notes)
    return {"ok": True}


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", "unknown")
    log.error("unhandled", extra={"request_id": rid}, exc_info=exc)
    return JSONResponse(status_code=500,
                        content={"detail": "Internal server error", "request_id": rid})


# app.mount("/", StaticFiles(directory="static", html=True), name="static")
app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="static")