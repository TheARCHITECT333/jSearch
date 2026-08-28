"""SSE progress streaming, driven through the real ASGI stack.

This is the seam the UI depends on for live progress, so it is exercised
end to end: bytes off the wire, parsed as `text/event-stream`, not by
calling the generator directly. A frame that isn't encodable as a string
(the class of bug that silently killed streaming before) fails here.

NOTE: `httpx.ASGITransport` runs the app to completion and *buffers* the
body - it does not hand back chunks as they are produced. So a test can
never read a frame mid-stream; instead it drives the search from a
concurrent task and asserts over the full frame sequence afterwards.
"""

import asyncio
import contextlib
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.services.search as search_module
from app.schemas import DiscoveredJob, LLMConfig
from app.services.search import SearchManager
from tests.conftest import VALID_MATCH_JSON, VALID_PROFILE_JSON, FakeLLM

LATEX = r"\documentclass{article}\begin{document}Go developer.\end{document}"
CFG = LLMConfig(provider="ollama", base_url="http://llm.test", model="fake-model")

JOB = {
    "title": "Backend Engineer",
    "url": "https://good.example/jobs/1",
    "location": "Bangalore",
    "description": "Go",
    "requirements": ["Go"],
    "source_url": "https://good.example/jobs",
}


def _browser_cm():
    @contextlib.asynccontextmanager
    async def cm():
        yield object()

    return cm


def parse_sse(raw: str) -> list[dict]:
    """Extract the JSON payload of every `data:` frame, ignoring heartbeats."""
    return [
        json.loads(line[len("data: ") :])
        for line in raw.splitlines()
        if line.startswith("data: ")
    ]


@pytest_asyncio.fixture
async def sse_client(monkeypatch, temp_db):
    """App wired to stubbed discovery, with a release gate so a search can be
    held in the `running` state while the test does something to it."""
    release = asyncio.Event()

    async def fake_discover(llm_arg, company, profile, browser, *, freshness="any",
                            locations=None, context_gate=None,
                            on_progress=None, on_status=None):
        if on_status:
            await on_status("Browsing careers site...")
        if on_progress:
            await on_progress(7, 1)
        await release.wait()
        return [DiscoveredJob.model_validate(JOB)]

    monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
    manager = SearchManager(browser_factory=_browser_cm())
    monkeypatch.setattr(search_module, "search_manager", manager)
    monkeypatch.setattr(
        "app.main.build_llm",
        lambda _cfg: FakeLLM([VALID_PROFILE_JSON, VALID_MATCH_JSON]),
    )
    monkeypatch.setattr("app.main.SSE_TICK_SECONDS", 0.01)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, manager, release


async def start_search(client) -> str:
    response = await client.post(
        "/api/search",
        json={
            "resume_latex": LATEX,
            "companies": [
                {"name": "GoodCorp", "careers_url": "https://good.example/jobs"}
            ],
            "llm": CFG.model_dump(),
        },
    )
    assert response.status_code == 200
    return response.json()["search_id"]


async def stream_frames(client, search_id: str, drive) -> list[dict]:
    """Consume the whole event stream while `drive()` runs concurrently.

    `drive` is what moves the search to a terminal state (releasing the
    stub, cancelling the search); without it the stream never ends.
    """
    collected: list[str] = []

    async def read() -> None:
        async with client.stream("GET", f"/api/search/{search_id}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            async for chunk in response.aiter_text():
                collected.append(chunk)

    reader = asyncio.create_task(read())
    await asyncio.sleep(0.05)  # let a few running frames accumulate
    await drive()
    await asyncio.wait_for(reader, timeout=10.0)
    return parse_sse("".join(collected))


class TestSearchEventStream:
    async def test_stream_emits_parseable_frames_until_terminal(self, sse_client):
        """The whole point of the endpoint: real frames, real JSON, ending in
        a terminal status carrying the results."""
        client, _manager, release = sse_client
        search_id = await start_search(client)

        async def drive():
            release.set()

        frames = await stream_frames(client, search_id, drive)

        assert frames, "stream produced no data frames"
        for frame in frames:
            assert frame["id"] == search_id
            assert isinstance(frame["companies"], list)
        assert frames[-1]["status"] == "completed"
        assert frames[-1]["results"][0]["job_title"] == "Backend Engineer"

    async def test_stream_reports_per_company_progress(self, sse_client):
        """Live per-company progress is the feature users actually watch, so
        assert the agent callbacks reach the wire - not just the final frame."""
        client, _manager, release = sse_client
        search_id = await start_search(client)

        async def drive():
            release.set()

        frames = await stream_frames(client, search_id, drive)

        running = [f for f in frames if f["status"] == "running"]
        assert running, "no running frame was streamed"
        progressed = [
            f["companies"][0]
            for f in running
            if f["companies"][0]["message"] == "Browsing careers site..."
        ]
        assert progressed, "the on_status callback never reached a frame"
        examined = [f["companies"][0]["jobs_examined"] for f in running]
        assert 7 in examined, "the on_progress callback never reached a frame"

    async def test_cancelled_search_reaches_a_terminal_frame(self, sse_client):
        """Cancellation must terminate the stream too, or the UI sits waiting
        on a search that is already over."""
        client, _manager, release = sse_client
        search_id = await start_search(client)

        async def drive():
            response = await client.post(f"/api/search/{search_id}/cancel")
            assert response.json()["cancelled"] is True

        frames = await stream_frames(client, search_id, drive)
        release.set()  # let the stubbed discovery unwind

        assert frames[-1]["status"] == "cancelled"
        assert "Cancelled" in (frames[-1]["error"] or "")

    async def test_unknown_search_streams_404(self, sse_client):
        client, _manager, release = sse_client
        release.set()
        response = await client.get("/api/search/does-not-exist/events")
        assert response.status_code == 404


class TestSearchBudget:
    """The budget must track the company count, or it goes stale the next
    time someone adds companies to companies.json."""

    def test_budget_scales_with_company_count(self):
        from app.agents.career_agent import OVERALL_TIMEOUT_S
        from app.services.search import search_budget_seconds

        # 43 companies at 4 at a time = 11 rounds; a fixed 1800s cannot cover it.
        big = search_budget_seconds(43, floor_s=1800, concurrency=4)
        assert big > 11 * OVERALL_TIMEOUT_S
        assert big > 1800

    def test_small_searches_keep_the_floor(self):
        from app.services.search import search_budget_seconds

        assert search_budget_seconds(1, floor_s=1800, concurrency=4) == 1800
        assert search_budget_seconds(0, floor_s=1800, concurrency=4) == 1800

    def test_manager_override_still_wins(self, temp_db):
        """Tests and operators can still pin an explicit budget."""
        manager = SearchManager(browser_factory=_browser_cm(), search_timeout_s=0.25)
        record = search_module._SearchRecord("abc", [])
        assert manager._budget_for(record) == 0.25

    @pytest.mark.parametrize(
        "count,concurrency,llm,rounds",
        [
            # A parallel model: browser slots are the limit, as before.
            (1, 4, 4, 1),
            (4, 4, 4, 1),
            (5, 4, 4, 2),
            (43, 4, 4, 11),
            # A serial model (the default, and what a stock Ollama is): four
            # companies browse at once but only one can think, so they finish
            # about as slowly as if they had run one after another. Sizing on
            # browser slots alone once granted 114 minutes for 140 minutes of
            # work and the search was killed just short of finishing.
            (1, 4, 1, 1),
            (4, 4, 1, 4),
            (5, 4, 1, 5),
            (43, 4, 1, 43),
            # Never more parallelism than there are companies to run.
            (2, 4, 8, 1),
        ],
    )
    def test_budget_round_arithmetic(self, count, concurrency, llm, rounds, monkeypatch):
        from app.agents.career_agent import OVERALL_TIMEOUT_S
        from app.llm import base as llm_base
        from app.services.search import search_budget_seconds

        monkeypatch.setattr(llm_base, "LLM_CONCURRENCY", llm)
        assert search_budget_seconds(
            count, floor_s=0, concurrency=concurrency
        ) == pytest.approx(rounds * OVERALL_TIMEOUT_S * 1.25)

    def test_a_serial_model_gets_a_far_bigger_budget_than_a_parallel_one(
        self, monkeypatch
    ):
        from app.llm import base as llm_base
        from app.services.search import search_budget_seconds

        monkeypatch.setattr(llm_base, "LLM_CONCURRENCY", 4)
        parallel = search_budget_seconds(50, floor_s=0, concurrency=4)
        monkeypatch.setattr(llm_base, "LLM_CONCURRENCY", 1)
        serial = search_budget_seconds(50, floor_s=0, concurrency=4)

        # 13 rounds vs 50: the whole point of the fix.
        assert serial > parallel * 3


class TestResultsStreamPerCompany:
    """Results must reach the UI as each company finishes, not at the end.

    Discovery and matching used to be two phases - browse everything, then
    match everything - so `results` stayed empty until the last site was
    done. On a long list that is a blank page for an hour, and a search
    stopped early showed nothing at all.
    """

    @pytest_asyncio.fixture
    async def two_company_client(self, monkeypatch, temp_db):
        gates = {"Fast": asyncio.Event(), "Slow": asyncio.Event()}

        async def fake_discover(llm_arg, company, profile, browser, *,
                                freshness="any", locations=None,
                                context_gate=None, on_progress=None,
                                on_status=None):
            await gates[company.name].wait()
            job = dict(JOB, url=f"https://{company.name.lower()}.example/jobs/1")
            return [DiscoveredJob.model_validate(job)]

        monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
        manager = SearchManager(browser_factory=_browser_cm())
        monkeypatch.setattr(search_module, "search_manager", manager)
        monkeypatch.setattr(
            "app.main.build_llm",
            lambda _cfg: FakeLLM(
                [VALID_PROFILE_JSON] + [VALID_MATCH_JSON] * 6
            ),
        )
        monkeypatch.setattr("app.main.SSE_TICK_SECONDS", 0.01)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, gates

    async def test_the_first_company_appears_before_the_second_finishes(
        self, two_company_client
    ):
        client, gates = two_company_client
        response = await client.post(
            "/api/search",
            json={
                "resume_latex": LATEX,
                "companies": [
                    {"name": "Fast", "careers_url": "https://fast.example/jobs"},
                    {"name": "Slow", "careers_url": "https://slow.example/jobs"},
                ],
                "llm": CFG.model_dump(),
            },
        )
        assert response.status_code == 200
        search_id = response.json()["search_id"]

        async def drive():
            gates["Fast"].set()
            await asyncio.sleep(0.25)   # Fast publishes while Slow is stuck
            gates["Slow"].set()

        frames = await stream_frames(client, search_id, drive)

        running_with_results = [
            f for f in frames if f["status"] == "running" and f["results"]
        ]
        assert running_with_results, (
            "no frame carried results while the search was still running - "
            "the UI would stay blank until every company finished"
        )
        # And the first one to land is the company that finished first.
        first = running_with_results[0]["results"]
        assert {r["company"] for r in first} == {"Fast"}

        terminal = frames[-1]
        assert terminal["status"] == "completed"
        assert {r["company"] for r in terminal["results"]} == {"Fast", "Slow"}
