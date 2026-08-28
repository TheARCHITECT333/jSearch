"""LLM abstraction.

Provider-specific HTTP code stays inside provider implementations.
Everything else talks to the abstract `LLM` interface.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)


# ---------------------------------------------------------------------------
# The LLM queue
# ---------------------------------------------------------------------------
# A stock Ollama serves one request at a time per model. Several company
# agents browsing concurrently would each fire at it unthrottled, and the
# loser could sit in the server's queue long enough to blow its HTTP timeout
# - starving one agent completely while another made steady progress.
#
# So calls take turns here instead. Browsing stays outside the gate: one
# agent still loads pages while another is thinking, which is where the real
# parallelism was anyway.
#
# Raise this only if the server really can serve N at once (Ollama's
# OLLAMA_NUM_PARALLEL, or a hosted API).
LLM_CONCURRENCY = max(1, int(os.getenv("LLM_CONCURRENCY", "1")))

_gate: asyncio.Semaphore | None = None
_gate_loop: asyncio.AbstractEventLoop | None = None

# Seconds this task has spent QUEUED rather than working. A caller running
# against a deadline must not be charged for another task's turn, so it can
# subtract this. Set per task: asyncio copies the context into every task,
# so two agents never see each other's total.
_queued_seconds: contextvars.ContextVar[float] = contextvars.ContextVar(
    "llm_queued_seconds", default=0.0
)


def llm_gate() -> asyncio.Semaphore:
    """The process-wide gate, bound lazily to the running loop.

    Created on first use rather than at import: a module-level Semaphore
    binds to whichever loop imported it, which breaks across the fresh loop
    every test gets.
    """
    global _gate, _gate_loop

    loop = asyncio.get_running_loop()
    if _gate is None or _gate_loop is not loop:
        _gate = asyncio.Semaphore(LLM_CONCURRENCY)
        _gate_loop = loop
    return _gate


def queued_seconds() -> float:
    """Total seconds this task has spent waiting for a turn."""
    return _queued_seconds.get()


@contextlib.asynccontextmanager
async def llm_slot():
    """Hold a turn at the LLM. Yields the seconds spent queued for it."""
    started = time.perf_counter()
    async with llm_gate():
        waited = time.perf_counter() - started
        if waited > 0.05:
            _queued_seconds.set(_queued_seconds.get() + waited)
        yield waited


@contextlib.asynccontextmanager
async def timed_llm_call(model: str):
    """Take a turn at the LLM and log what the call cost.

    `wait` and `gen` are reported separately on purpose - they diagnose
    different problems. High `wait` means too many callers for one server
    (raise LLM_CONCURRENCY only if it really can serve more). High `gen`
    means the model itself is slow, and no amount of queueing will help.
    """
    async with llm_slot() as waited:
        started = time.perf_counter()
        try:
            yield
        finally:
            generated = time.perf_counter() - started
            logger.info(
                "llm call: model=%s wait=%.1fs gen=%.1fs",
                model or "?",
                waited,
                generated,
                extra={
                    "event": "llm.call",
                    "model": model,
                    "queued_s": round(waited, 1),
                    "duration_s": round(generated, 1),
                },
            )


class LLMError(Exception):
    """Friendly, user-presentable LLM failure."""


class LLMAvailabilityError(LLMError):
    """Could not reach the LLM server at all."""


class LLMInvalidOutputError(LLMError):
    """The LLM responded, but never produced valid structured output."""


class LLM(ABC):
    """Minimal async chat interface implemented by every provider."""

    @abstractmethod
    async def generate(self, system: str, user: str) -> str:
        """Return the assistant message for one system+user exchange."""

    @abstractmethod
    async def close(self) -> None:
        """Release underlying HTTP resources."""

    @property
    def model_name(self) -> str:
        return ""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Best-effort extraction of a JSON value from an LLM response.

    Handles raw JSON, ```fenced``` blocks, and leading prose before the
    first `{` or `[`.
    """
    if text is None:
        raise ValueError("empty response")

    stripped = text.strip()

    fenced = _JSON_FENCE_RE.search(stripped)
    if fenced:
        candidate = fenced.group(1).strip()
    else:
        candidate = stripped

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost braces/brackets span.
    for open_char, close_char in (("{", "}"), ("[", "]")):
        start = candidate.find(open_char)
        end = candidate.rfind(close_char)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError("response does not contain valid JSON")


async def generate_validated(
    llm: LLM,
    system: str,
    user: str,
    model_cls: type[TModel],
    *,
    retries: int = 1,
) -> TModel:
    """Ask the LLM for JSON matching `model_cls`.

    On invalid output the request is retried (default: once) with feedback.
    Raises `LLMInvalidOutputError` if every attempt fails validation.
    """
    prompt = user
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        started = time.perf_counter()
        raw = await llm.generate(system, prompt)
        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            data = extract_json(raw)
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            parsed = model_cls.model_validate(data)
        except Exception as exc:  # noqa: BLE001 - any failure triggers retry
            last_error = exc
            # Worth a line: a model that always needs the retry is costing
            # double, and that is invisible without this.
            logger.warning(
                "%s returned invalid %s on attempt %d/%d (%.0fms): %s",
                llm.model_name or "llm",
                model_cls.__name__,
                attempt + 1,
                retries + 1,
                elapsed_ms,
                exc,
                extra={
                    "event": "llm.invalid_output",
                    "model": llm.model_name,
                    "schema": model_cls.__name__,
                    "attempt": attempt + 1,
                    "duration_ms": round(elapsed_ms),
                },
            )
            prompt = (
                f"{user}\n\n"
                "IMPORTANT: Your previous response was invalid and rejected.\n"
                f"Problem: {exc}\n"
                "Respond again with ONLY a single valid JSON object that matches "
                "the requested schema. No prose, no markdown fences."
            )
        else:
            logger.debug(
                "%s produced %s in %.0fms",
                llm.model_name or "llm",
                model_cls.__name__,
                elapsed_ms,
                extra={
                    "event": "llm.completed",
                    "model": llm.model_name,
                    "schema": model_cls.__name__,
                    "attempt": attempt + 1,
                    "duration_ms": round(elapsed_ms),
                },
            )
            return parsed

    raise LLMInvalidOutputError(
        f"The LLM returned invalid structured data after {retries + 1} attempts: {last_error}"
    )
