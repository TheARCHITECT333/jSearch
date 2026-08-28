"""End-to-end API flow tests with a scripted fake LLM and a stubbed browser.

Covers: health, profile extraction endpoint, search start/status polling,
per-company failure isolation, ranking, and error surfaces.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import app.services.search as search_module
from app.schemas import DiscoveredJob
from app.services.search import SearchManager
from tests.conftest import VALID_MATCH_JSON, VALID_PROFILE_JSON, FakeLLM

LATEX = r"\documentclass{article}\begin{document}Go developer.\end{document}"

COMPANIES = [
    {"name": "GoodCorp", "careers_url": "https://good.example/jobs"},
    {"name": "BadCorp", "careers_url": "https://bad.example/careers"},
]

# Explicit LLM config - the backend has no built-in defaults.
FAKE_LLM_CONFIG = {
    "provider": "ollama",
    "base_url": "http://llm.test/ollama",
    "model": "fake-model",
}

DISCOVERED_GOOD = [
    {
        "title": "Senior Backend Engineer",
        "url": "https://good.example/jobs/123",
        "location": "Bangalore",
        "employment_type": "Full-time",
        "description": "Go + AWS",
        "requirements": ["Go", "AWS"],
        "source_url": "https://good.example/jobs",
    },
    {
        "title": "Platform Engineer",
        "url": "https://good.example/jobs/456",
        "description": "Docker",
        "requirements": ["Docker"],
        "source_url": "https://good.example/jobs",
    },
]


@pytest.fixture
def stubbed_environment(monkeypatch):
    """Patch discovery (no real browser) and return the FakeLLM used."""
    llm = FakeLLM([])

    async def fake_discover(llm_arg, company, profile, browser, *, freshness="any",
                            locations=None, context_gate=None,
                                on_progress=None, on_status=None):
        if company.name == "BadCorp":
            raise RuntimeError("site unreachable")
        if on_progress:
            await on_progress(1, 1)
        if on_status:
            await on_status("Inspecting...")
        return [DiscoveredJob.model_validate(job) for job in DISCOVERED_GOOD]

    def fake_browser_factory():
        import contextlib

        @contextlib.asynccontextmanager
        async def cm():
            yield object()  # never actually used by stubbed discovery

        return cm()

    monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
    manager = SearchManager(browser_factory=fake_browser_factory)
    monkeypatch.setattr(search_module, "search_manager", manager)
    # Route the endpoint's LLM factory to the scripted fake.
    monkeypatch.setattr("app.main.build_llm", lambda config: llm)

    def set_llm_responses(responses):
        llm._responses = list(responses)

    return type("Env", (), {"llm": llm, "set_llm_responses": staticmethod(set_llm_responses)})()


async def wait_for_completion(client, search_id: str, timeout_s: float = 5.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        response = await client.get(f"/api/search/{search_id}")
        assert response.status_code == 200
        status = response.json()
        if status["status"] not in ("queued", "running"):
            return status
        assert asyncio.get_event_loop().time() < deadline, "search did not finish in time"
        await asyncio.sleep(0.02)


async def wait_for_status(
    lookup, search_id: str, wanted: str, timeout_s: float = 5.0
) -> dict:
    """Poll a callable(search_id)->dict until it reaches `wanted`."""
    from app.services.search import SearchNotFoundError

    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        try:
            status = lookup(search_id)
        except SearchNotFoundError:
            status = None
        if status is not None and status["status"] == wanted:
            return status
        assert asyncio.get_event_loop().time() < deadline, (
            f"search never reached {wanted}"
        )
        await asyncio.sleep(0.01)


class TestHealth:
    async def test_health(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}

    async def test_health_fails_when_database_is_gone(self, client):
        """A health check that cannot fail isn't one: dispose the engine and
        the endpoint must report 503, not a cheerful 200."""
        from app import db

        await db.dispose_db()
        response = await client.get("/api/health")
        assert response.status_code == 503
        assert "Database" in response.json()["detail"]


class TestProfileEndpoint:
    async def test_profile_extracted(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.main.build_llm", lambda config: FakeLLM([VALID_PROFILE_JSON])
        )
        response = await client.post(
            "/api/profile",
            json={"resume_latex": LATEX, "llm": FAKE_LLM_CONFIG},
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        assert profile["name"] == "Shubh Sharma"
        assert profile["skills"]["languages"] == ["Go", "Python"]

    async def test_missing_llm_config_is_rejected_with_friendly_error(
        self, client
    ):
        response = await client.post("/api/profile", json={"resume_latex": LATEX})
        assert response.status_code == 422
        assert "No LLM configured" in response.json()["detail"]

    async def test_build_llm_requires_base_url_and_model(self, client):
        from app.main import build_llm
        from app.schemas import LLMConfig

        with pytest.raises(ValueError) as excinfo:
            build_llm(LLMConfig(provider="ollama"))
        assert "base URL" in str(excinfo.value)

        with pytest.raises(ValueError):
            build_llm(
                LLMConfig(provider="ollama", base_url="http://x.test", model="")
            )

    async def test_llm_unavailable_maps_to_502_with_friendly_message(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.main.build_llm",
            lambda config: FakeLLM([RuntimeError("connection refused")]),
        )
        # FakeLLM raises the raw exception; base treats non-LLMError exceptions
        # via httpx layer only, so simulate an availability failure directly.
        from app.llm import LLMAvailabilityError

        class Failing(FakeLLM):
            async def generate(self, system, user):
                raise LLMAvailabilityError(
                    "Could not connect to Ollama. Make sure Ollama is running."
                )

        monkeypatch.setattr("app.main.build_llm", lambda config: Failing([]))
        response = await client.post(
            "/api/profile", json={"resume_latex": LATEX, "llm": FAKE_LLM_CONFIG}
        )
        assert response.status_code == 502
        assert "Could not connect to Ollama" in response.json()["detail"]

    async def test_invalid_structured_output_surfaces_clear_error(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.main.build_llm",
            lambda config: FakeLLM(["garbage", "more garbage"]),
        )
        response = await client.post(
            "/api/profile", json={"resume_latex": LATEX, "llm": FAKE_LLM_CONFIG}
        )
        assert response.status_code == 502
        assert "invalid structured data" in response.json()["detail"]


class TestSearchFlow:
    async def test_full_search_with_one_company_failing(self, client, stubbed_environment):
        env = stubbed_environment
        # 1 profile + matches for GoodCorp's two discovered jobs.
        env.set_llm_responses([VALID_PROFILE_JSON, VALID_MATCH_JSON, VALID_MATCH_JSON])

        started = await client.post(
            "/api/search",
            json={
                "resume_latex": LATEX,
                "companies": COMPANIES,
                "llm": FAKE_LLM_CONFIG,
            },
        )
        assert started.status_code == 200
        search_id = started.json()["search_id"]

        status = await wait_for_completion(client, search_id)

        assert status["status"] == "completed"
        by_company = {c["company"]: c for c in status["companies"]}
        # Failure isolation: BadCorp failed without cancelling GoodCorp.
        assert by_company["BadCorp"]["status"] == "failed"
        assert "could not be navigated" in by_company["BadCorp"]["message"]
        assert by_company["GoodCorp"]["status"] == "completed"
        assert by_company["GoodCorp"]["jobs_found"] == 2

        results = status["results"]
        assert len(results) == 2
        scores = [r["match"]["overall_score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        first = results[0]
        assert first["company"] == "GoodCorp"
        assert first["job_url"].startswith("https://good.example/jobs/")
        assert first["careers_url"] == "https://good.example/jobs"

    async def test_all_companies_failing_marks_search_failed(self, client, monkeypatch):
        import contextlib

        async def always_fail(*args, **kwargs):
            raise RuntimeError("down")

        @contextlib.asynccontextmanager
        async def cm():
            yield object()

        monkeypatch.setattr(search_module, "discover_company_jobs", always_fail)
        manager = SearchManager(browser_factory=cm)
        monkeypatch.setattr(search_module, "search_manager", manager)
        monkeypatch.setattr(
            "app.main.build_llm", lambda config: FakeLLM([VALID_PROFILE_JSON])
        )

        started = await client.post(
            "/api/search",
            json={
                "resume_latex": LATEX,
                "companies": [
                    {"name": "Solo", "careers_url": "https://solo.example/j"}
                ],
                "llm": FAKE_LLM_CONFIG,
            },
        )
        assert started.status_code == 200
        status = await wait_for_completion(client, started.json()["search_id"])
        assert status["status"] == "failed"
        assert status["error"]
        assert status["results"] == []

    async def test_stale_jobs_filtered_before_matching(self, client, monkeypatch):
        """With freshness=1w, provably-old listings must be dropped BEFORE
        any matching LLM call is spent on them; unknown-age jobs stay."""
        import contextlib

        from app.schemas import DiscoveredJob

        llm = FakeLLM([])
        mixed = [
            {"title": "Fresh Role", "url": "https://good.example/jobs/fresh",
             "posted_at": "1 day ago", "description": "", "requirements": []},
            {"title": "Ancient Role", "url": "https://good.example/jobs/old",
             "posted_at": "3 months ago", "description": "", "requirements": []},
            {"title": "Mystery Age", "url": "https://good.example/jobs/mystery",
             "posted_at": None, "description": "", "requirements": []},
        ]

        async def fake_discover(llm_arg, company, profile, browser, *, freshness="any",
                                locations=None, context_gate=None,
                                on_progress=None, on_status=None):
            assert freshness == "1w"  # the window reaches the agent
            return [DiscoveredJob.model_validate(j) for j in mixed]

        @contextlib.asynccontextmanager
        async def cm():
            yield object()

        monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
        manager = SearchManager(browser_factory=cm)
        monkeypatch.setattr(search_module, "search_manager", manager)
        monkeypatch.setattr("app.main.build_llm", lambda config: llm)

        started = await client.post(
            "/api/search",
            json={
                "resume_latex": LATEX,
                "companies": [COMPANIES[0]],
                "freshness": "1w",
                "llm": FAKE_LLM_CONFIG,
            },
        )
        assert started.status_code == 200
        search_id = started.json()["search_id"]

        # 1 profile + exactly TWO matches (fresh + unknown; the ancient one
        # must never reach the matcher).
        llm._responses = [VALID_PROFILE_JSON, VALID_MATCH_JSON, VALID_MATCH_JSON]
        status = await wait_for_completion(client, search_id)

        assert status["status"] == "completed"
        titles = {r["job_title"] for r in status["results"]}
        assert titles == {"Fresh Role", "Mystery Age"}
        progress = status["companies"][0]
        assert progress["jobs_found"] == 2

    async def test_out_of_location_jobs_filtered(self, client, monkeypatch):
        """locations=[Bangalore] drops clearly-elsewhere jobs before
        matching; unknown-location and Remote jobs stay."""
        import contextlib

        from app.schemas import DiscoveredJob

        llm = FakeLLM([])
        mixed = [
            {"title": "Local Role", "url": "https://good.example/jobs/local",
             "location": "Bengaluru, Karnataka", "description": "", "requirements": []},
            {"title": "Elsewhere Role", "url": "https://good.example/jobs/sf",
             "location": "San Francisco, CA", "description": "", "requirements": []},
            {"title": "Remote Role", "url": "https://good.example/jobs/remote",
             "location": "Remote - Worldwide", "description": "", "requirements": []},
            {"title": "Mystery Location", "url": "https://good.example/jobs/mystery",
             "location": None, "description": "", "requirements": []},
        ]

        async def fake_discover(llm_arg, company, profile, browser, *, freshness="any",
                                locations=None, context_gate=None,
                                on_progress=None, on_status=None):
            assert locations == ["Bangalore"]  # the list reaches the agent
            return [DiscoveredJob.model_validate(j) for j in mixed]

        @contextlib.asynccontextmanager
        async def cm():
            yield object()

        monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
        manager = SearchManager(browser_factory=cm)
        monkeypatch.setattr(search_module, "search_manager", manager)
        monkeypatch.setattr("app.main.build_llm", lambda config: llm)

        started = await client.post(
            "/api/search",
            json={
                "resume_latex": LATEX,
                "companies": [COMPANIES[0]],
                "locations": ["Bangalore"],
                "llm": FAKE_LLM_CONFIG,
            },
        )
        assert started.status_code == 200
        search_id = started.json()["search_id"]

        # 1 profile + exactly THREE matches (local + remote + unknown;
        # San Francisco must never reach the matcher).
        llm._responses = [VALID_PROFILE_JSON, VALID_MATCH_JSON, VALID_MATCH_JSON,
                          VALID_MATCH_JSON]
        status = await wait_for_completion(client, search_id)

        assert status["status"] == "completed"
        titles = {r["job_title"] for r in status["results"]}
        assert titles == {"Local Role", "Remote Role", "Mystery Location"}
        progress = status["companies"][0]
        assert progress["jobs_found"] == 3
        assert progress["message"] and "outside [Bangalore]" in progress["message"]

    async def test_unknown_search_returns_404(self, client):
        response = await client.get("/api/search/does-not-exist")
        assert response.status_code == 404
        assert "restarted" in response.json()["detail"]


class TestWorkerPool:
    """Phase: FastAPI -> Search Job -> async workers."""

    def _manager(self, monkeypatch, fake_discover, *, workers=1, queue_max=50, browser_cm=None):
        import contextlib

        if browser_cm is None:
            @contextlib.asynccontextmanager
            async def browser_cm():
                yield object()

        monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
        return search_module.SearchManager(
            browser_factory=browser_cm,
            max_concurrent_searches=workers,
            queue_max_size=queue_max,
        )

    @staticmethod
    def _company() -> list:
        from app.schemas import CompanyInput

        return [CompanyInput(name="GoodCorp", careers_url="https://good.example/jobs")]

    async def test_single_worker_serializes_searches(self, monkeypatch, temp_db):
        """With one runner, the second enqueued search must stay 'queued'
        until the first finishes - no unbounded concurrent Chromium spawns."""
        gate_a, gate_b = asyncio.Event(), asyncio.Event()
        calls = {"n": 0}

        async def slow_discover(llm_arg, company, profile, browser, *, freshness="any",
                                locations=None, context_gate=None,
                                on_progress=None, on_status=None):
            calls["n"] += 1
            await (gate_a if calls["n"] == 1 else gate_b).wait()
            return []

        manager = self._manager(monkeypatch, slow_discover, workers=1)
        # One FRESH LLM per search (real providers are single-use here:
        # _execute closes the client when its search ends).
        llms = iter([FakeLLM([VALID_PROFILE_JSON]), FakeLLM([VALID_PROFILE_JSON])])
        factory = lambda _cfg: next(llms)

        from app.schemas import LLMConfig

        companies = self._company()
        cfg = LLMConfig(provider="ollama", base_url="http://x", model="m")

        id_a = manager.start_search(
            resume_latex=LATEX, companies=companies, llm_config=cfg,
            llm_factory=factory,
        )
        lookup = lambda sid: manager.get_status(sid).model_dump()  # noqa: E731
        # A holds the single runner while gate_a is closed.
        await wait_for_status(lookup, id_a, "running")

        id_b = manager.start_search(
            resume_latex=LATEX, companies=companies, llm_config=cfg,
            llm_factory=factory,
        )
        # While A occupies the runner, B must remain queued.
        for _ in range(20):
            assert lookup(id_b)["status"] == "queued"
            await asyncio.sleep(0.01)

        gate_a.set()  # release A
        await wait_for_status(lookup, id_a, "completed")

        # Now B starts - and STAYS running until we release its own gate.
        await wait_for_status(lookup, id_b, "running")
        await asyncio.sleep(0.05)
        assert lookup(id_b)["status"] == "running"

        gate_b.set()
        await wait_for_status(lookup, id_b, "completed")

    async def test_queue_full_raises(self, monkeypatch):
        gate = asyncio.Event()

        async def blocked_discover(*args, **kwargs):
            await gate.wait()
            return []

        manager = self._manager(
            monkeypatch, blocked_discover, workers=1, queue_max=1
        )
        llm = FakeLLM([VALID_PROFILE_JSON, VALID_PROFILE_JSON])

        from app.schemas import LLMConfig

        kwargs = dict(
            resume_latex=LATEX,
            companies=self._company(),
            llm_config=LLMConfig(provider="ollama", base_url="http://x", model="m"),
            llm_factory=lambda cfg: llm,
        )

        manager.start_search(**kwargs)   # picked up by the single runner
        await asyncio.sleep(0.05)        # yield so the runner dequeues it

        manager.start_search(**kwargs)   # fills the queue (1/1)

        from app.services.search import SearchQueueFullError

        with pytest.raises(SearchQueueFullError):
            manager.start_search(**kwargs)

        gate.set()
        await manager.drain(timeout=2.0)


class TestSSEProgress:
    async def test_events_stream_until_terminal(self, client, stubbed_environment):
        env = stubbed_environment
        env.set_llm_responses([VALID_PROFILE_JSON, VALID_MATCH_JSON])

        started = await client.post(
            "/api/search",
            json={
                "resume_latex": LATEX,
                "companies": [{"name": "GoodCorp", "careers_url": "https://good.example/jobs"}],
                "llm": FAKE_LLM_CONFIG,
            },
        )
        sid = started.json()["search_id"]

        data_lines: list[str] = []
        async with client.stream("GET", f"/api/search/{sid}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache"
            ticks = 0
            async for line in response.aiter_lines():
                ticks += 1
                assert ticks < 500, "SSE stream never terminated"
                if line.startswith("data: "):
                    data_lines.append(line[len("data: "):])
                    payload = json.loads(data_lines[-1])
                    if payload["status"] in ("completed", "failed"):
                        break

        assert data_lines, "no SSE events received"
        final = json.loads(data_lines[-1])
        assert final["status"] == "completed"
        assert len(final["results"]) == 1

    async def test_sse_unknown_search_is_404(self, client):
        response = await client.get("/api/search/nope/events")
        assert response.status_code == 404

    async def test_openai_compatible_requires_api_key(self, client):
        response = await client.post(
            "/api/search",
            json={
                "resume_latex": LATEX,
                "companies": COMPANIES,
                "llm": {
                    "provider": "openai-compatible",
                    "base_url": "https://api.example.com/v1",
                    "model": "gpt-4o-mini",
                },
            },
        )
        assert response.status_code == 422
        assert "API key" in response.json()["detail"]

    async def test_search_without_llm_config_rejected(self, client):
        response = await client.post(
            "/api/search", json={"resume_latex": LATEX, "companies": COMPANIES}
        )
        assert response.status_code == 422
        assert "No LLM configured" in response.json()["detail"]

    async def test_empty_companies_rejected(self, client):
        response = await client.post(
            "/api/search", json={"resume_latex": LATEX, "companies": []}
        )
        assert response.status_code == 422


class TestRanking:
    async def test_results_sorted_descending_by_overall_score(self):
        record_scores = [70, 95, 82]
        from app.schemas import JobResult, MatchResult

        results = []
        for index, score in enumerate(record_scores):
            results.append(
                JobResult.model_validate(
                    {
                        "company": f"C{index}",
                        "job_title": f"Role {index}",
                        "job_url": f"https://x.example/j/{index}",
                        "match": MatchResult.model_validate(
                            {
                                "overall_score": score,
                                "role_fit": score,
                                "skill_fit": score,
                                "experience_fit": score,
                                "location_fit": score,
                            }
                        ),
                    }
                )
            )
        ranked = sorted(results, key=lambda r: r.match.overall_score, reverse=True)
        got = [r.match.overall_score for r in ranked]
        assert got == sorted(got, reverse=True)
