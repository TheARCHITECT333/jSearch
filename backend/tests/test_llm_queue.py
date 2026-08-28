"""The LLM queue, and the failures it exists to prevent.

Background: two company agents browsing at once both fired at the same
Ollama server, which serves one request at a time. The loser sat in the
server's queue past the 180s HTTP timeout, `ask_llm_json` silently retried
it, and 360s of a 420s budget vanished - one company made steady progress
while the other went completely silent and returned nothing.
"""

import asyncio
import time

import pytest

from app.agents.career_agent import ask_llm_json
from app.llm import LLMAvailabilityError, LLMError
from app.llm.base import llm_gate, llm_slot, queued_seconds


class RecordingLLM:
    """Records when each generation starts and ends, so overlap is visible."""

    def __init__(self, delay: float = 0.05, replies=None):
        self.delay = delay
        self.replies = list(replies or [])
        self.spans: list[tuple[float, float]] = []
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "recorder"

    async def generate(self, system: str, user: str) -> str:
        self.calls += 1
        async with llm_slot():
            started = time.perf_counter()
            await asyncio.sleep(self.delay)
            self.spans.append((started, time.perf_counter()))
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return '{"action": "finish"}'

    async def close(self) -> None:
        return None


def _overlaps(spans) -> bool:
    ordered = sorted(spans)
    return any(ordered[i][1] > ordered[i + 1][0] for i in range(len(ordered) - 1))


class TestSerialisation:
    async def test_concurrent_callers_never_generate_at_the_same_time(self):
        # This is the whole point: one server, one request at a time.
        llm = RecordingLLM(delay=0.05)
        await asyncio.gather(*(llm.generate("s", f"u{i}") for i in range(6)))
        assert len(llm.spans) == 6
        assert not _overlaps(llm.spans)

    async def test_the_gate_is_rebuilt_for_a_new_event_loop(self):
        # A module-level Semaphore binds to whichever loop imported it, which
        # would break every test after the first. It must bind lazily.
        gate = llm_gate()
        assert gate is llm_gate()  # stable within one loop

    async def test_waiting_for_a_turn_is_recorded_against_the_waiter_only(self):
        llm = RecordingLLM(delay=0.2)

        async def caller() -> float:
            before = queued_seconds()
            await llm.generate("s", "u")
            return queued_seconds() - before

        waits = await asyncio.gather(*(asyncio.create_task(caller()) for _ in range(2)))
        # One went first and waited for nothing; the other queued behind it.
        # Crucially each task sees only its OWN wait - contextvars are copied
        # per task, so agents never inherit each other's totals.
        assert min(waits) < 0.1
        assert max(waits) >= 0.1


class TestAskLlmJsonRetries:
    async def test_malformed_json_is_retried_once(self):
        llm = RecordingLLM(replies=["not json at all", '{"action": "finish"}'])
        assert await ask_llm_json(llm, "s", "u") == {"action": "finish"}
        assert llm.calls == 2

    async def test_still_malformed_after_the_retry_returns_none(self):
        llm = RecordingLLM(replies=["nope", "still nope"])
        assert await ask_llm_json(llm, "s", "u") is None
        assert llm.calls == 2

    async def test_a_timeout_is_not_retried(self):
        # The regression that starved a whole company: retrying a request
        # that already burned the 180s HTTP timeout costs another 180s.
        llm = RecordingLLM(replies=[LLMError("Ollama timed out after 180s")])
        with pytest.raises(LLMError):
            await ask_llm_json(llm, "s", "u")
        assert llm.calls == 1

    async def test_an_unreachable_server_is_not_retried(self):
        llm = RecordingLLM(replies=[LLMAvailabilityError("Could not connect")])
        with pytest.raises(LLMAvailabilityError):
            await ask_llm_json(llm, "s", "u")
        assert llm.calls == 1
