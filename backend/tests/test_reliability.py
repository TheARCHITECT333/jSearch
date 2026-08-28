"""Reliability tests.

Proves: bounded company concurrency (no 40-Chromium stampede), the global
browser gate, discovery retry, search timeout, and user cancellation.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

import app.services.search as search_module
from app.schemas import CompanyInput, LLMConfig
from app.services.browser_pool import make_context_gate
from tests.conftest import VALID_PROFILE_JSON, FakeLLM

LATEX = r"\documentclass{article}\begin{document}Go developer.\end{document}"
CFG = LLMConfig(provider="ollama", base_url="http://x", model="m")


def companies(n: int) -> list[CompanyInput]:
    return [
        CompanyInput(name=f"Corp{i}", careers_url=f"https://corp{i}.example/jobs")
        for i in range(n)
    ]


def _browser_cm():
    @contextlib.asynccontextmanager
    async def cm():
        yield object()

    return cm


async def wait_terminal(manager, search_id: str, timeout_s: float = 8.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        status = manager.get_status(search_id).model_dump()
        if status["status"] not in ("queued", "running"):
            return status
        assert asyncio.get_event_loop().time() < timeout_s + deadline
        await asyncio.sleep(0.02)


class TestCompanyScheduler:
    async def test_concurrency_is_bounded(self, monkeypatch, temp_db):
        """12 companies with slots=3 must never run more than 3 at once."""
        state = {"active": 0, "peak": 0}

        async def fake_discover(llm_arg, company, profile, browser, *, freshness="any",
                                locations=None, context_gate=None,
                                on_progress=None, on_status=None):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.05)
            state["active"] -= 1
            return []

        monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
        manager = search_module.SearchManager(
            browser_factory=_browser_cm(), company_concurrency=3
        )
        llm = FakeLLM([VALID_PROFILE_JSON])

        search_id = manager.start_search(
            resume_latex=LATEX,
            companies=companies(12),
            llm_config=CFG,
            llm_factory=lambda c: llm,
        )
        final = await wait_terminal(manager, search_id)

        assert final["status"] == "completed"
        assert state["peak"] <= 3, f"stampede detected: peak={state['peak']}"
        assert state["active"] == 0

    async def test_many_companies_all_processed(self, monkeypatch, temp_db):
        """40 companies with a small scheduler still all get processed."""
        processed: list[str] = []

        async def fake_discover(llm_arg, company, profile, browser, *, freshness="any",
                                locations=None, context_gate=None,
                                on_progress=None, on_status=None):
            processed.append(company.name)
            return []

        monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
        manager = search_module.SearchManager(
            browser_factory=_browser_cm(), company_concurrency=5
        )
        llm = FakeLLM([VALID_PROFILE_JSON])

        final = await wait_terminal(
            manager,
            manager.start_search(
                resume_latex=LATEX,
                companies=companies(40),
                llm_config=CFG,
                llm_factory=lambda c: llm,
            ),
            timeout_s=15.0,
        )
        assert final["status"] == "completed"
        assert len(processed) == 40


class TestBrowserGate:
    def test_gate_bounds_holders(self):
        async def scenario():
            gate = make_context_gate(2)

            active = {"n": 0, "peak": 0}

            async def hold():
                async with gate:
                    active["n"] += 1
                    active["peak"] = max(active["peak"], active["n"])
                    await asyncio.sleep(0.03)
                    active["n"] -= 1

            await asyncio.gather(*(hold() for _ in range(7)))
            assert active["peak"] <= 2
            assert active["n"] == 0

        asyncio.run(scenario())

    def test_manager_uses_global_gate_by_default(self):
        from app.services.browser_pool import global_context_gate

        manager = search_module.SearchManager(browser_factory=_browser_cm())
        assert manager._context_gate is global_context_gate


class TestDiscoveryRetry:
    async def test_transient_failure_retried_then_completed(self, monkeypatch, temp_db):
        attempts = {"n": 0}

        async def flaky_discover(llm_arg, company, profile, browser, *, freshness="any",
                                 locations=None, context_gate=None,
                                 on_progress=None, on_status=None):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient network blip")
            return []

        monkeypatch.setattr(search_module, "discover_company_jobs", flaky_discover)
        monkeypatch.setattr(search_module, "DISCOVERY_RETRY_BACKOFF_S", 0.01)
        manager = search_module.SearchManager(browser_factory=_browser_cm())

        sid = manager.start_search(
            resume_latex=LATEX,
            companies=companies(1),
            llm_config=CFG,
            llm_factory=lambda c: FakeLLM([VALID_PROFILE_JSON]),
        )
        final = await wait_terminal(manager, sid)

        assert final["status"] == "completed"
        assert attempts["n"] == 2  # exactly one retry

    async def test_permanent_failure_stops_after_two_attempts(self, monkeypatch, temp_db):
        attempts = {"n": 0}

        async def dead_discover(llm_arg, company, profile, browser, *, freshness="any",
                                locations=None, context_gate=None,
                                on_progress=None, on_status=None):
            attempts["n"] += 1
            raise RuntimeError("site is down")

        monkeypatch.setattr(search_module, "discover_company_jobs", dead_discover)
        monkeypatch.setattr(search_module, "DISCOVERY_RETRY_BACKOFF_S", 0.01)
        manager = search_module.SearchManager(browser_factory=_browser_cm())

        sid = manager.start_search(
            resume_latex=LATEX,
            companies=companies(1),
            llm_config=CFG,
            llm_factory=lambda c: FakeLLM([VALID_PROFILE_JSON]),
        )
        final = await wait_terminal(manager, sid)

        assert final["status"] == "failed"  # no successful company at all
        by_company = {c["company"]: c for c in final["companies"]}
        assert by_company["Corp0"]["status"] == "failed"
        assert attempts["n"] == DISCOVERY_ATTEMPTS_EXPECTED


DISCOVERY_ATTEMPTS_EXPECTED = search_module.DISCOVERY_ATTEMPTS


class TestSearchTimeout:
    async def test_stuck_search_times_out(self, monkeypatch, temp_db):
        block = asyncio.Event()

        async def stuck_discover(llm_arg, company, profile, browser, *, freshness="any",
                                 locations=None, context_gate=None,
                                 on_progress=None, on_status=None):
            await block.wait()
            return []

        monkeypatch.setattr(search_module, "discover_company_jobs", stuck_discover)
        manager = search_module.SearchManager(
            browser_factory=_browser_cm(), search_timeout_s=0.2
        )

        sid = manager.start_search(
            resume_latex=LATEX,
            companies=companies(1),
            llm_config=CFG,
            llm_factory=lambda c: FakeLLM([VALID_PROFILE_JSON]),
        )
        final = await wait_terminal(manager, sid, timeout_s=5.0)

        assert final["status"] == "failed"
        assert "time budget" in (final["error"] or "")
        block.set()  # let the cancelled coroutine unwind cleanly


class TestCancellation:
    async def test_cancel_running_search(self, monkeypatch, temp_db):
        gate_a = asyncio.Event()

        async def gated_discover(llm_arg, company, profile, browser, *, freshness="any",
                                 locations=None, context_gate=None,
                                 on_progress=None, on_status=None):
            await gate_a.wait()
            return []

        monkeypatch.setattr(search_module, "discover_company_jobs", gated_discover)
        manager = search_module.SearchManager(browser_factory=_browser_cm())

        sid = manager.start_search(
            resume_latex=LATEX,
            companies=companies(1),
            llm_config=CFG,
            llm_factory=lambda c: FakeLLM([VALID_PROFILE_JSON]),
        )
        # Wait until actually running inside discovery.
        while manager.get_status(sid).companies[0].status != "running":
            await asyncio.sleep(0.01)

        assert manager.cancel_search(sid) is True
        final = await wait_terminal(manager, sid, timeout_s=5.0)
        assert final["status"] == "cancelled"
        assert final["error"] == "Cancelled by user."

        gate_a.set()  # unwind cleanly
        await manager.drain(timeout=2.0)
        assert manager.get_status(sid).status == "cancelled"

    async def test_cancel_queued_search_skips_it(self, monkeypatch, temp_db):
        gate = asyncio.Event()
        started: list[str] = []

        async def gated_discover(llm_arg, company, profile, browser, *, freshness="any",
                                 locations=None, context_gate=None,
                                 on_progress=None, on_status=None):
            started.append(company.name[0])
            await gate.wait()
            return []

        monkeypatch.setattr(search_module, "discover_company_jobs", gated_discover)
        manager = search_module.SearchManager(
            browser_factory=_browser_cm(), max_concurrent_searches=1
        )
        llms = iter([FakeLLM([VALID_PROFILE_JSON]), FakeLLM([VALID_PROFILE_JSON])])
        factory = lambda _c: next(llms)  # noqa: E731

        id_a = manager.start_search(
            resume_latex=LATEX, companies=companies(1), llm_config=CFG,
            llm_factory=factory,
        )
        await asyncio.sleep(0.05)  # let runner A pick it up and block on gate

        id_b = manager.start_search(
            resume_latex=LATEX, companies=companies(1), llm_config=CFG,
            llm_factory=factory,
        )
        assert manager.get_status(id_b).status == "queued"

        assert manager.cancel_search(id_b) is True
        assert manager.get_status(id_b).status == "cancelled"

        gate.set()
        await wait_terminal(manager, id_a)
        # B was skipped by the runner without ever starting discovery.
        await asyncio.sleep(0.1)
        assert manager.get_status(id_b).status == "cancelled"

    async def test_cancelling_unknown_or_terminal_is_false(self, temp_db):
        manager = search_module.SearchManager(browser_factory=_browser_cm())
        assert manager.cancel_search("ghost") is False

    async def test_double_cancel_returns_false(self, monkeypatch, temp_db):
        gate = asyncio.Event()

        async def gated_discover(*args, **kwargs):
            await gate.wait()
            return []

        monkeypatch.setattr(search_module, "discover_company_jobs", gated_discover)
        manager = search_module.SearchManager(browser_factory=_browser_cm())
        sid = manager.start_search(
            resume_latex=LATEX, companies=companies(1), llm_config=CFG,
            llm_factory=lambda c: FakeLLM([VALID_PROFILE_JSON]),
        )
        assert manager.cancel_search(sid) is True
        assert manager.cancel_search(sid) is False
        gate.set()
        await manager.drain(timeout=2.0)


def _browser_cm():
    @contextlib.asynccontextmanager
    async def cm():
        yield object()

    return cm


class TestFailureClassification:
    """Retrying the wrong failure is how a 6-minute problem became 13.

    A second attempt re-runs the whole company with a fresh budget and no
    memory of what it already saw. That is worth it for a flaky page load,
    and pure waste when the model itself was the bottleneck.
    """

    def test_a_browser_failure_is_worth_one_retry(self):
        from app.services.search import _is_retryable

        assert _is_retryable(RuntimeError("site unreachable")) is True

    def test_a_timeout_is_not_retried(self):
        import asyncio

        from app.services.search import _is_retryable

        assert _is_retryable(asyncio.TimeoutError()) is False

    def test_a_slow_model_is_not_retried_even_when_rewrapped(self):
        # discovery.py rewraps everything as CareerAgentError, so the real
        # cause survives only in the `raise ... from` chain.
        from app.agents.career_agent import CareerAgentError
        from app.llm import LLMError
        from app.services.search import _is_retryable

        try:
            try:
                raise LLMError("Ollama timed out after 180s")
            except LLMError as exc:
                raise CareerAgentError("career agent failed") from exc
        except CareerAgentError as wrapped:
            assert _is_retryable(wrapped) is False

    def test_a_wrapped_browser_failure_is_still_retryable(self):
        from app.agents.career_agent import CareerAgentError
        from app.services.search import _is_retryable

        try:
            try:
                raise RuntimeError("site unreachable")
            except RuntimeError as exc:
                raise CareerAgentError("career agent failed") from exc
        except CareerAgentError as wrapped:
            assert _is_retryable(wrapped) is True


class TestFailureMessage:
    def test_a_site_that_would_not_load_says_so(self):
        from app.services.search import _failure_message

        assert "navigated" in _failure_message(RuntimeError("boom"))

    def test_running_out_of_time_does_not_blame_the_site(self):
        # The site was browsed fine for six minutes; saying it "could not be
        # navigated" sends people to debug the wrong thing.
        import asyncio

        from app.services.search import _failure_message

        message = _failure_message(asyncio.TimeoutError())
        assert "time" in message.lower()
        assert "navigated" not in message

    def test_a_model_failure_names_the_model(self):
        from app.agents.career_agent import CareerAgentError
        from app.llm import LLMAvailabilityError
        from app.services.search import _failure_message

        try:
            try:
                raise LLMAvailabilityError("Could not connect to Ollama")
            except LLMAvailabilityError as exc:
                raise CareerAgentError("career agent failed") from exc
        except CareerAgentError as wrapped:
            assert "model" in _failure_message(wrapped).lower()


class TestEmptyRunIsExplained:
    """A company that returns nothing must say why, not show a bare tick.

    Once a budget timeout returns partial results instead of raising, an
    agent that found nothing completes "successfully" with zero jobs. Left
    alone that renders as a green tick and no explanation, which reads as
    "this site genuinely has no jobs for you" - usually false.
    """

    async def test_a_run_that_found_nothing_keeps_the_agents_explanation(
        self, monkeypatch
    ):
        from app.schemas import CompanyProgress
        from app.services import search as search_module

        progress = CompanyProgress(company="Amazon")

        async def fake_discover(*args, **kwargs):
            await kwargs["on_status"]("Out of time for this company; keeping 0 job(s) found.")
            return []

        monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
        manager = search_module.SearchManager()
        record = search_module._SearchRecord("s1", [], locations=[])
        jobs = await manager._browse_with_retry(
            record, object(), search_module.CompanyInput(
                name="Amazon", careers_url="https://amazon.example/jobs"
            ), None, None, progress
        )

        assert jobs == []
        assert progress.status == "completed"
        assert "Out of time" in (progress.message or "")

    async def test_a_silent_empty_run_still_gets_a_reason(self, monkeypatch):
        from app.schemas import CompanyProgress
        from app.services import search as search_module

        progress = CompanyProgress(company="Amazon")

        async def fake_discover(*args, **kwargs):
            return []

        monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
        manager = search_module.SearchManager()
        record = search_module._SearchRecord("s1", [], locations=[])
        await manager._browse_with_retry(
            record, object(), search_module.CompanyInput(
                name="Amazon", careers_url="https://amazon.example/jobs"
            ), None, None, progress
        )

        assert progress.message == "Nothing found on this site."
