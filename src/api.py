"""
FastAPI web UI backend for the UK Home Insurance Claims Triage Agent.

Exposes four endpoints:
  GET  /              → serve ui/index.html
  GET  /claims        → list of sample claims from data/sample_claims.json
  POST /submit        → queue a claim for processing, return job_id
  GET  /stream/{job}  → SSE stream: real-time log lines + final result

Streaming architecture (cert note — Context Management):
  The coordinator emits structured logs via Python's logging module. We
  capture them per-request using a RoutingHandler on the root logger that
  reads a thread-local request_id stamped by PerRequestFilter. Each SSE
  stream reads from its own queue.Queue, so concurrent claims don't bleed
  log messages into each other. The async generator offloads queue.get()
  to a thread pool so the uvicorn event loop stays free during the 15–30s
  blocking API call.
"""

import asyncio
import json
import logging
import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

from dotenv import load_dotenv

# Must be called before any src.* imports so env vars are available to client.py
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from src.agents.coordinator import CoordinatorResult, run as coordinator_run
from src.client import make_client
from src.models import AgentInput

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).parent.parent
SAMPLE_CLAIMS_PATH = _ROOT / "data" / "sample_claims.json"
UI_PATH = _ROOT / "ui" / "index.html"

# ---------------------------------------------------------------------------
# App + thread pool
# ---------------------------------------------------------------------------

app = FastAPI(title="UK Home Insurance Claims Triage")
_executor = ThreadPoolExecutor(max_workers=4)

# ---------------------------------------------------------------------------
# Per-request log routing
#
# Cert note — Context Management / Hooks pattern:
# The RoutingHandler is analogous to a PostToolUse hook: it intercepts every
# log record and decides what to do with it (route or discard). The filter
# stamps request_id onto the record without modifying the coordinator code —
# same principle as a hook that wraps tool execution transparently.
# ---------------------------------------------------------------------------

_thread_local = threading.local()

# Registry: job_id → {"queue": queue.Queue}
_jobs: dict[str, dict] = {}


class PerRequestFilter(logging.Filter):
    """Stamps each LogRecord with the current thread's request_id."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(_thread_local, "request_id", None)  # type: ignore[attr-defined]
        return True


class RoutingHandler(logging.Handler):
    """Routes log records to the matching per-job queue."""

    def emit(self, record: logging.LogRecord) -> None:
        job_id = getattr(record, "request_id", None)
        if job_id and job_id in _jobs:
            try:
                msg = self.format(record)
                _jobs[job_id]["queue"].put(("log", msg))
            except Exception:
                pass


# Install once at startup — the filter stamps, the handler routes.
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
_routing_handler = RoutingHandler()
_routing_handler.setFormatter(_fmt)
_routing_handler.addFilter(PerRequestFilter())
logging.getLogger().addHandler(_routing_handler)

# Allow INFO from src.* so coordinator log lines flow through to the routing handler.
# The root logger defaults to WARNING, which silently drops INFO records before
# they ever reach our handler — this is the fix.
logging.getLogger("src").setLevel(logging.INFO)

# Suppress noisy loggers so they don't appear in the claim log feed
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Thread worker
# ---------------------------------------------------------------------------


def _run_coordinator(job_id: str, claim: AgentInput) -> None:
    """
    Runs in ThreadPoolExecutor. Sets thread-local request_id so the
    RoutingHandler can direct this thread's log records to the right queue.
    """
    _thread_local.request_id = job_id
    q = _jobs[job_id]["queue"]
    try:
        client = make_client()
        result: CoordinatorResult = coordinator_run(claim, client)
        result_dict = {
            "request_id": result.request_id,
            "escalated": result.escalated,
            "escalation_reason": result.escalation_reason,
            "retry_count": result.retry_count,
            "triage": result.triage.model_dump() if result.triage else None,
            "action_result": result.action_result,
            "error": result.error,
        }
        q.put(("result", json.dumps(result_dict, default=str)))
    except Exception as exc:
        logging.getLogger(__name__).error("Coordinator failed for job %s: %s", job_id, exc)
        q.put(("error", str(exc)))
    finally:
        q.put(None)  # Sentinel — signals SSE generator to close


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/")
async def serve_ui() -> FileResponse:
    return FileResponse(UI_PATH)


@app.get("/claims")
async def list_claims() -> list:
    return json.loads(SAMPLE_CLAIMS_PATH.read_text(encoding="utf-8"))


@app.post("/submit")
async def submit_claim(claim_data: dict) -> dict:
    # Strip internal annotation field if present
    claim_data.pop("_scenario", None)

    # Generate a fresh request_id so UI-submitted claims are traceable
    if not claim_data.get("request_id"):
        claim_data["request_id"] = f"UI-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    if not claim_data.get("timestamp"):
        claim_data["timestamp"] = datetime.now(timezone.utc).isoformat()
    if not claim_data.get("channel"):
        claim_data["channel"] = "web_ui"

    try:
        claim = AgentInput(**claim_data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"queue": queue.Queue()}

    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_coordinator, job_id, claim)

    return {"job_id": job_id}


@app.get("/stream/{job_id}")
async def stream_events(job_id: str) -> StreamingResponse:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        q = _jobs[job_id]["queue"]
        loop = asyncio.get_event_loop()
        try:
            while True:
                # Offload blocking queue.get() to thread pool so event loop stays free
                item = await loop.run_in_executor(None, q.get)
                if item is None:
                    yield "event: done\ndata: {}\n\n"
                    break
                event_type, data = item
                yield f"event: {event_type}\ndata: {json.dumps({'message': data})}\n\n"
        except GeneratorExit:
            pass
        finally:
            _jobs.pop(job_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
