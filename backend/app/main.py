"""Personal Agentic Job Hunter - FastAPI backend.

Searches are JOBS: POST /api/search enqueues them, a bounded pool of async
runner tasks executes them in-process, and progress streams to the UI over
SSE (GET /api/search/{id}/events) with polling as fallback.

Active searches live in memory; only history (jobs, matches, searches,
cached profiles) is persisted, in an embedded SQLite database.

The backend has NO built-in LLM defaults: everything it needs (provider,
base URL, model, optional API key) is supplied per request by the frontend.
It never contacts any LLM server on startup, and never persists an API key.
"""

import asyncio
import contextlib
import json
import logging
import os
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .llm import (
    LLM,
    LLMAvailabilityError,
    LLMError,
    OllamaLLM,
    OpenAICompatibleLLM,
)
from .logging_setup import configure_logging, request_context
from .schemas import (
    CompanyInput,
    LLMConfig,
    ProfileRequest,
    ProfileResponse,
    ScoreRequest,
    SearchRequest,
    StartSearchResponse,
)
from .services.resume import ResumeExtractionError, extract_profile
from .services.scoring import score_resume
from .services.search import SearchQueueFullError
from .services import search as search_service

configure_logging()
logger = logging.getLogger(__name__)

MAX_CONCURRENT_SEARCHES = int(os.getenv("SEARCH_WORKERS", "2"))
QUEUE_MAX_SIZE = int(os.getenv("SEARCH_QUEUE_MAX", "50"))
SSE_TICK_SECONDS = float(os.getenv("SSE_TICK_SECONDS", "1.0"))

# Shared, configured instance used by all API endpoints.
search_service.search_manager = search_service.SearchManager(
    max_concurrent_searches=MAX_CONCURRENT_SEARCHES,
    queue_max_size=QUEUE_MAX_SIZE,
)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup: migrate the database / mark orphaned searches. Shutdown:
    give queued and in-flight searches a brief window, then cancel the rest."""
    from .db import init_db

    await init_db()
    yield
    logger.info("shutting down: draining search workers...")
    await search_service.search_manager.drain(timeout=5.0)
    logger.info("search workers drained.")


app = FastAPI(title="Personal Job Hunter API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths logged only when they fail - the Docker healthcheck hits /api/health
# every 30s and a successful probe is not news.
_QUIET_PATHS = {"/api/health"}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """One line per request, with a correlation id every log line emitted
    while handling it also carries.

    Note: for a streaming response this measures time to the first byte -
    `call_next` returns once the headers are out, not when the SSE stream
    finally closes.
    """
    with request_context() as request_id:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "%s %s failed after %.1fms",
                request.method,
                request.url.path,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 1),
                },
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id

        quiet = request.url.path in _QUIET_PATHS and response.status_code < 400
        if not quiet:
            logger.log(
                logging.WARNING if response.status_code >= 500 else logging.INFO,
                "%s %s -> %d (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 1),
                },
            )
        return response


def build_llm(config: LLMConfig) -> LLM:
    """Create the provider client from the request's explicit config.

    Raises ValueError with a friendly message when required fields are
    missing - there are no silent defaults pointing at any server.
    """
    base_url = (config.base_url or "").strip()
    model = (config.model or "").strip()

    if not base_url:
        raise ValueError("Set the LLM base URL in the UI before starting.")
    if not model:
        raise ValueError("Set the LLM model in the UI before starting.")

    if config.provider == "ollama":
        return OllamaLLM(base_url=base_url, model=model, api_key=config.api_key)
    return OpenAICompatibleLLM(base_url=base_url, model=model, api_key=config.api_key)


def _require_llm_config(request_llm: LLMConfig | None) -> LLMConfig:
    if request_llm is None:
        raise HTTPException(
            status_code=422,
            detail="No LLM configured. Pick a provider and fill in its base "
            "URL and model in the UI first.",
        )
    return request_llm


_SEARCH_NOT_FOUND = (
    "Search not found. It may have expired because the backend restarted."
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    """Liveness + readiness: the database must actually be reachable."""
    from .db import ping

    if not await ping():
        raise HTTPException(status_code=503, detail="Database is not reachable.")
    return {"status": "ok", "database": "ok"}


@app.post("/api/profile", response_model=ProfileResponse)
async def create_profile(request: ProfileRequest) -> ProfileResponse:
    llm_config = _require_llm_config(request.llm)

    try:
        llm = build_llm(llm_config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        profile = await extract_profile(llm, request.resume_latex)
    except ResumeExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMAvailabilityError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMError as exc:
        logger.exception("profile endpoint failure")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await llm.close()
    return ProfileResponse(profile=profile)


MAX_PDF_BYTES = 10 * 1024 * 1024


@app.post("/api/resume/pdf")
async def resume_pdf_to_text(request: Request) -> dict:
    """Raw PDF body in, plain text out. The UI then treats it like a .tex.

    Link targets are appended because resumes often hide the GitHub URL
    behind an icon - and scoring needs it.
    """
    import pymupdf

    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF is larger than 10 MB.")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
            links = {l["uri"] for page in doc for l in page.get_links() if l.get("uri")}
    except Exception as exc:  # noqa: BLE001 - any parse failure is the user's file
        raise HTTPException(status_code=422, detail="Could not read this PDF.") from exc
    if links:
        text += "\n\nLinks:\n" + "\n".join(sorted(links))
    if len(text.strip()) < 40:
        raise HTTPException(
            status_code=422,
            detail="No readable text in this PDF (scanned image?). Try the LaTeX source.",
        )
    return {"text": text}


@app.post("/api/score")
async def score(request: ScoreRequest) -> dict:
    llm_config = _require_llm_config(request.llm)
    try:
        llm = build_llm(llm_config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return await score_resume(llm, request.resume_latex, request.level)
    except LLMError as exc:
        logger.exception("score endpoint failure")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await llm.close()


@app.post("/api/search", response_model=StartSearchResponse)
async def start_search(request: SearchRequest) -> StartSearchResponse:
    llm_config = _require_llm_config(request.llm)

    if llm_config.provider == "openai-compatible" and not (
        llm_config.api_key or ""
    ).strip():
        raise HTTPException(
            status_code=422,
            detail="An API key is required for OpenAI-compatible providers.",
        )

    companies = [
        CompanyInput.model_validate({"name": c.name, "careers_url": c.careers_url})
        for c in request.companies
    ]

    try:
        search_id = search_service.search_manager.start_search(
            resume_latex=request.resume_latex,
            companies=companies,
            llm_config=llm_config,
            llm_factory=build_llm,
            freshness=request.freshness,
            locations=request.locations,
        )
    except SearchQueueFullError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StartSearchResponse(search_id=search_id)


@app.get("/api/search/{search_id}")
async def get_search(search_id: str):
    try:
        return search_service.search_manager.get_status(search_id).model_dump()
    except search_service.SearchNotFoundError:
        pass  # not in memory - maybe it's history from before a restart

    from .services import store

    historical = await store.load_search_history(search_id)
    if historical is None:
        raise HTTPException(status_code=404, detail=_SEARCH_NOT_FOUND) from None
    return historical.model_dump()


@app.post("/api/search/{search_id}/cancel")
async def cancel_search(search_id: str):
    """Cancel a queued or running search."""
    cancelled = search_service.search_manager.cancel_search(search_id)
    if not cancelled and not _search_exists(search_id):
        raise HTTPException(status_code=404, detail=_SEARCH_NOT_FOUND) from None
    return {"id": search_id, "cancelled": cancelled}


def _search_exists(search_id: str) -> bool:
    try:
        search_service.search_manager.get_status(search_id)
        return True
    except search_service.SearchNotFoundError:
        return False


@app.get("/api/searches")
async def list_searches(limit: int = 20):
    """Recent search history (persisted across restarts)."""
    from .services import store

    return await store.list_recent_searches(limit=min(max(limit, 1), 100))


# ---------------------------------------------------------------------------
# SSE progress streaming
# ---------------------------------------------------------------------------

_TERMINAL_STATES = {"completed", "failed", "cancelled"}


async def _search_event_stream(search_id: str):
    """Yield `data: <json>\\n\\n` SSE events whenever the search's serialized
    status changes; ends after a terminal state. Heartbeat comments keep
    proxies from closing idle connections."""
    last_fingerprint: object | None = None
    ticks_since_send = 0
    while True:
        try:
            status = search_service.search_manager.get_status(search_id)
        except search_service.SearchNotFoundError:
            # Search pruned mid-stream (e.g. restart): tell the client and stop.
            yield "event: gone\ndata: {}\n\n"
            return

        # Cheap change test before the expensive one. Results now stream in
        # company by company, so the payload carries every job description
        # found so far - serializing that once a second for an hour-long
        # search just to discover nothing changed would burn the event loop
        # the agents are running on. Results only ever append, so their
        # length is enough to notice a change.
        fingerprint = (
            status.status,
            status.error,
            len(status.results),
            tuple(
                (c.company, c.status, c.jobs_examined, c.jobs_found, c.message)
                for c in status.companies
            ),
        )
        if fingerprint != last_fingerprint:
            last_fingerprint = fingerprint
            payload = json.dumps(status.model_dump())
            ticks_since_send = 0
            yield f"data: {payload}\n\n"
            if status.status in _TERMINAL_STATES:
                return
        else:
            ticks_since_send += 1
            if ticks_since_send % 15 == 0:
                yield ": ping\n\n"
        await asyncio.sleep(SSE_TICK_SECONDS)


@app.get("/api/search/{search_id}/events")
async def stream_search_events(search_id: str):
    """Server-Sent Events stream of live search progress."""
    try:
        search_service.search_manager.get_status(search_id)
    except search_service.SearchNotFoundError:
        raise HTTPException(status_code=404, detail=_SEARCH_NOT_FOUND) from None

    return StreamingResponse(
        _search_event_stream(search_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Disable proxy buffering so events arrive immediately.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
