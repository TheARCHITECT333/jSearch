"""Logging configuration.

Three things the default `basicConfig` could not give us:

1. **Correlation.** A search fans out over several companies at once, and
   two searches can run concurrently, so log lines from unrelated work
   interleave. `search_id` / `company` / `request_id` ride along in
   contextvars (which follow `await` and `asyncio.create_task` correctly)
   and are attached to every record automatically - call sites don't have
   to thread them through.

2. **A machine-readable mode.** `LOG_FORMAT=json` emits one JSON object per
   line for grepping or shipping; the default `text` stays readable.

3. **Secret redaction.** `AGENTS.md` says API keys are never logged. This
   enforces it in code: the formatted line - message, args and traceback -
   is scrubbed before it reaches a handler, so an unlucky `logger.exception`
   cannot leak a key.

Stdlib only, on purpose: `logging` + `contextvars` cover all of it.
"""

import contextlib
import contextvars
import json
import logging
import os
import re
import sys
import time
import uuid
from typing import Any, Iterator

# --- Correlation context ---------------------------------------------------
# contextvars, not thread-locals: this is an asyncio app and every search
# runs as its own task.

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
_search_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "search_id", default=None
)
_company: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "company", default=None
)

CONTEXT_FIELDS = ("request_id", "search_id", "company")


@contextlib.contextmanager
def request_context(request_id: str | None = None) -> Iterator[str]:
    """Tag every log line emitted while handling one HTTP request."""
    value = request_id or uuid.uuid4().hex[:8]
    token = _request_id.set(value)
    try:
        yield value
    finally:
        _request_id.reset(token)


@contextlib.contextmanager
def search_context(search_id: str) -> Iterator[None]:
    """Tag every log line emitted while one search runs."""
    token = _search_id.set(search_id)
    try:
        yield
    finally:
        _search_id.reset(token)


@contextlib.contextmanager
def company_context(company: str) -> Iterator[None]:
    """Tag every log line emitted while browsing one company."""
    token = _company.set(company)
    try:
        yield
    finally:
        _company.reset(token)


def current_context() -> dict[str, str]:
    """The correlation fields currently in scope (only the ones that are set)."""
    values = {
        "request_id": _request_id.get(),
        "search_id": _search_id.get(),
        "company": _company.get(),
    }
    return {k: v for k, v in values.items() if v}


class ContextFilter(logging.Filter):
    """Attach the current correlation fields to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = current_context()
        for field in CONTEXT_FIELDS:
            setattr(record, field, context.get(field))
        record.context = context
        return True


# --- Redaction -------------------------------------------------------------

REDACTED = "***REDACTED***"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # api_key=abc / api_key: 'abc' / "api_key": "abc"
    # The value class excludes backslashes so a redaction inside an
    # already-escaped string cannot swallow the escape character.
    re.compile(
        r"""(?ix)
        (["']?\b(?:api[_-]?key|apikey|authorization|token|secret|password)\b["']?
         \s*[:=]\s*)
        (["']?)([^\s,'"})\]\\]+)(\2)
        """
    ),
    # Authorization: Bearer <token>
    re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._\-]{8,})"),
    # Provider-style keys that are recognisable on their own.
    re.compile(r"\bsk-[A-Za-z0-9._\-]{8,}"),
    # Credentials embedded in a URL: https://user:pass@host
    re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^/\s:@]+:)([^/\s@]+)(@)"),
)


def redact(text: str) -> str:
    """Replace anything that looks like a credential with a placeholder."""
    if not text:
        return text
    text = _SECRET_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}{m.group(4)}", text)
    text = _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    text = _SECRET_PATTERNS[2].sub(REDACTED, text)
    text = _SECRET_PATTERNS[3].sub(lambda m: f"{m.group(1)}{REDACTED}{m.group(3)}", text)
    return text


# --- Formatters ------------------------------------------------------------

# Attributes every LogRecord carries; anything else a caller passed via
# `extra=` is treated as a structured field worth emitting.
_STANDARD_RECORD_KEYS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {
    "asctime",
    "message",
    "taskName",
    "context",
    # uvicorn attaches an ANSI-coloured duplicate of its own message.
    "color_message",
    *CONTEXT_FIELDS,
}


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_KEYS and not key.startswith("_")
    }


class TextFormatter(logging.Formatter):
    """Human-readable, with correlation shown before the message.

    Before, not after: messages are often multi-line (Pydantic validation
    errors, tracebacks), and a suffix would end up buried under the last
    line of the exception instead of next to the log line it belongs to.
    """

    default_time_format = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        parts = [f"{k}={v}" for k, v in current_context().items()]
        parts += [f"{k}={v}" for k, v in _extra_fields(record).items()]
        record = logging.makeLogRecord(record.__dict__)
        if parts:
            record.msg = f"[{' '.join(parts)}] {record.getMessage()}"
            record.args = ()
        return redact(super().format(record))


def _scrub(value: Any) -> Any:
    """Redact a field value, converting anything exotic to a string first.

    Redaction happens BEFORE `json.dumps`, never after: scrubbing serialized
    JSON can eat an escape character and produce a line that no longer
    parses.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact(value)
    return redact(str(value))


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)
            )
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": _scrub(record.getMessage()),
        }
        payload.update(current_context())
        for key, value in _extra_fields(record).items():
            payload[key] = _scrub(value)

        if record.exc_info:
            payload["exception"] = _scrub(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = _scrub(self.formatStack(record.stack_info))

        return json.dumps(payload, default=str)


# --- Setup -----------------------------------------------------------------

_configured = False


def configure_logging(
    level: str | None = None, fmt: str | None = None, *, force: bool = False
) -> None:
    """Install handlers on the root logger. Idempotent - importing the app
    twice (as the tests do) must not double every line."""
    global _configured
    if _configured and not force:
        return

    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    fmt = (fmt or os.getenv("LOG_FORMAT", "text")).lower()

    formatter: logging.Formatter
    if fmt == "json":
        formatter = JsonFormatter()
    else:
        formatter = TextFormatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
        )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn's access log duplicates our request middleware (which also
    # records duration and request_id), so keep only its warnings.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv = logging.getLogger(name)
        uv.handlers = []
        uv.propagate = True

    # Third-party chatter that is never useful here at INFO. Alembic in
    # particular logs a dozen plugin lines on every single startup; app/db.py
    # logs the one fact that matters (which revision we ended up on).
    for noisy in ("httpx", "httpcore", "asyncio", "alembic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
