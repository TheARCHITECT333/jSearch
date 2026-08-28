"""Logging behaviour: correlation, structure, and secret redaction.

The redaction tests matter most - `AGENTS.md` promises API keys are never
logged, and this is the code that has to keep that promise.
"""

import asyncio
import io
import json
import logging

import pytest

from app.logging_setup import (
    REDACTED,
    ContextFilter,
    JsonFormatter,
    TextFormatter,
    company_context,
    configure_logging,
    current_context,
    redact,
    request_context,
    search_context,
)


@pytest.fixture
def capture():
    """A logger writing through our formatter into a buffer."""

    def _make(formatter: logging.Formatter):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        handler.addFilter(ContextFilter())

        logger = logging.getLogger(f"test.{id(stream)}")
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        return logger, stream

    return _make


class TestRedaction:
    @pytest.mark.parametrize(
        "text",
        [
            "api_key=sk-supersecretvalue123",
            "api_key: 'sk-supersecretvalue123'",
            '{"api_key": "sk-supersecretvalue123"}',
            "apikey=sk-supersecretvalue123",
            "Authorization: Bearer sk-supersecretvalue123",
            "token=sk-supersecretvalue123",
            "password=sk-supersecretvalue123",
        ],
    )
    def test_secrets_never_survive(self, text):
        result = redact(text)
        assert "supersecretvalue123" not in result
        assert REDACTED in result

    def test_bare_provider_key_is_caught(self):
        assert "sk-abcdef1234567890" not in redact("failed for sk-abcdef1234567890")

    def test_url_credentials_are_caught(self):
        result = redact("connecting to https://user:hunter2@llm.example/v1")
        assert "hunter2" not in result
        assert "llm.example" in result  # the useful part survives

    def test_ordinary_text_is_untouched(self):
        text = "search 4f2a completed with 12 results in 31.4s"
        assert redact(text) == text

    def test_base_url_without_credentials_survives(self):
        text = "connecting to http://localhost:11434"
        assert redact(text) == text

    def test_key_in_an_exception_traceback_is_redacted(self, capture):
        logger, stream = capture(JsonFormatter())
        try:
            raise RuntimeError("upstream rejected api_key=sk-leakedsecret999")
        except RuntimeError:
            logger.exception("llm call failed")

        payload = json.loads(stream.getvalue())
        assert "sk-leakedsecret999" not in json.dumps(payload)
        assert REDACTED in payload["exception"]

    def test_key_passed_as_a_log_argument_is_redacted(self, capture):
        logger, stream = capture(TextFormatter("%(message)s"))
        logger.info("config: %s", {"model": "qwen3", "api_key": "sk-leakedsecret999"})

        assert "sk-leakedsecret999" not in stream.getvalue()


class TestCorrelation:
    def test_context_is_attached_to_records(self, capture):
        logger, stream = capture(JsonFormatter())
        with search_context("abc123"), company_context("Stripe"):
            logger.info("browsing")

        payload = json.loads(stream.getvalue())
        assert payload["search_id"] == "abc123"
        assert payload["company"] == "Stripe"
        assert payload["message"] == "browsing"

    def test_absent_context_is_omitted_not_null(self, capture):
        logger, stream = capture(JsonFormatter())
        logger.info("no context here")

        payload = json.loads(stream.getvalue())
        assert "search_id" not in payload
        assert "company" not in payload

    def test_context_is_restored_after_the_block(self):
        assert current_context() == {}
        with search_context("s1"):
            assert current_context()["search_id"] == "s1"
            with search_context("s2"):
                assert current_context()["search_id"] == "s2"
            assert current_context()["search_id"] == "s1"
        assert current_context() == {}

    async def test_concurrent_searches_do_not_bleed_into_each_other(self, capture):
        """The reason contextvars are used instead of a module global: two
        searches run at once and their log lines must stay separable."""
        logger, stream = capture(JsonFormatter())

        async def run(search_id: str, company: str) -> None:
            with search_context(search_id), company_context(company):
                for _ in range(5):
                    logger.info("step")
                    await asyncio.sleep(0)  # force interleaving

        await asyncio.gather(run("aaa", "Google"), run("bbb", "Stripe"))

        lines = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert len(lines) == 10
        # Every line kept its own search's company - no cross-contamination.
        for line in lines:
            expected = "Google" if line["search_id"] == "aaa" else "Stripe"
            assert line["company"] == expected

    async def test_context_survives_task_boundaries(self, capture):
        logger, stream = capture(JsonFormatter())

        async def child() -> None:
            logger.info("from a child task")

        with search_context("parent-search"):
            await asyncio.gather(child(), child())

        for line in stream.getvalue().splitlines():
            assert json.loads(line)["search_id"] == "parent-search"

    def test_request_context_generates_an_id(self):
        with request_context() as request_id:
            assert len(request_id) == 8
            assert current_context()["request_id"] == request_id

    def test_request_context_accepts_a_supplied_id(self):
        with request_context("deadbeef") as request_id:
            assert request_id == "deadbeef"


class TestFormatters:
    def test_json_line_is_one_valid_object(self, capture):
        logger, stream = capture(JsonFormatter())
        logger.warning("careful")

        payload = json.loads(stream.getvalue())
        assert payload["level"] == "WARNING"
        assert payload["message"] == "careful"
        assert payload["timestamp"].endswith("Z")

    def test_extra_fields_become_structured_fields(self, capture):
        logger, stream = capture(JsonFormatter())
        logger.info(
            "done", extra={"event": "search.finished", "results": 12, "duration_s": 3.5}
        )

        payload = json.loads(stream.getvalue())
        assert payload["event"] == "search.finished"
        assert payload["results"] == 12
        assert payload["duration_s"] == 3.5

    def test_text_format_prefixes_context_readably(self, capture):
        logger, stream = capture(TextFormatter("%(levelname)s %(message)s"))
        with search_context("abc123"), company_context("Stripe"):
            logger.info("browsing")

        line = stream.getvalue().strip()
        assert line == "INFO [search_id=abc123 company=Stripe] browsing"

    def test_context_stays_visible_on_a_multiline_message(self, capture):
        """Context goes BEFORE the message: a Pydantic error or traceback
        would otherwise bury it under the last line."""
        logger, stream = capture(TextFormatter("%(levelname)s %(message)s"))
        with search_context("abc123"):
            logger.warning("validation failed:\nline one\nline two")

        first_line = stream.getvalue().splitlines()[0]
        assert "search_id=abc123" in first_line

    def test_text_format_still_interpolates_args(self, capture):
        logger, stream = capture(TextFormatter("%(message)s"))
        with search_context("abc123"):
            logger.info("found %d job(s) at %s", 7, "Stripe")

        assert stream.getvalue().strip() == "[search_id=abc123] found 7 job(s) at Stripe"

    def test_text_format_stays_clean_without_context(self, capture):
        logger, stream = capture(TextFormatter("%(levelname)s %(message)s"))
        logger.info("plain")

        assert stream.getvalue().strip() == "INFO plain"


class TestConfigure:
    def test_is_idempotent(self):
        """Importing the app twice must not double every log line."""
        root = logging.getLogger()
        original = root.handlers[:]
        try:
            configure_logging(force=True)
            first = len(root.handlers)
            configure_logging()
            configure_logging()
            assert len(root.handlers) == first == 1
        finally:
            root.handlers = original

    def test_json_mode_selects_the_json_formatter(self):
        root = logging.getLogger()
        original, original_level = root.handlers[:], root.level
        try:
            configure_logging(fmt="json", force=True)
            assert isinstance(root.handlers[0].formatter, JsonFormatter)
        finally:
            root.handlers, root.level = original, original_level

    def test_level_is_applied(self):
        root = logging.getLogger()
        original, original_level = root.handlers[:], root.level
        try:
            configure_logging(level="WARNING", force=True)
            assert root.level == logging.WARNING
        finally:
            root.handlers, root.level = original, original_level
