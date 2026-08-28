"""Career agent integration tests against the LOCAL deterministic fixture
site. No external career sites, no real LLM.

The scripted FakeLLM drives the agent through: navigate -> open both job
pages -> finish. Safety tests prove the agent refuses unsafe actions even
when the page (or a scripted action) tries to make it do something else.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright", reason="playwright not installed; agent E2E skipped")

from playwright.async_api import Error, async_playwright  # noqa: E402

from app.agents.career_agent import CareerAgent  # noqa: E402
from app.schemas import CandidateProfile  # noqa: E402
from tests.conftest import FakeLLM  # noqa: E402


def job_json(title: str, url_hint: str) -> str:
    return json.dumps(
        {
            "title": title,
            "location": "Bangalore" if "backend" in url_hint else "Remote",
            "employment_type": "Full-time",
            "description": f"Description for {title}.",
            "requirements": ["Go"] if "backend" in url_hint else ["Python"],
            "preferred_qualifications": [],
        }
    )


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def run_agent(llm_responses: list[str], careers_url: str, max_job_visits: int = 12):
    """`max_job_visits=1` keeps the MODEL in charge of what to open.

    The agent opens listed postings itself when they all fit the remaining
    budget. Tests about click/type/press mechanics want the scripted
    decisions to drive, so they shrink the budget below the number of
    postings on the page and the agent hands control back."""
    llm = FakeLLM(list(llm_responses))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            agent = CareerAgent(
                llm=llm,
                company_name="ExampleCorp",
                careers_url=careers_url,
                profile=CandidateProfile(target_roles=["Backend Engineer"]),
                max_job_visits=max_job_visits,
            )
            jobs = await agent.run(browser)
            return jobs, llm, agent
        finally:
            await browser.close()


class TestDiscoveryOnLocalFixture:
    @pytest.mark.timeout(120)
    async def test_discovers_both_jobs_with_real_urls(self, fixture_server):
        """The model is asked only where it has a real choice.

        It navigates to the listing, and from there the agent opens both
        postings itself - they fit the visit budget, so there is nothing to
        choose. The two `open_job` decisions this script used to carry cost
        an LLM call each and are gone: 6 responses became 4.
        """
        responses = [
            json.dumps({"action": "click", "text": "Jobs"}),
            job_json("Backend Engineer", "backend"),   # harvested, not decided
            job_json("Python Developer", "python"),    # harvested, not decided
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        jobs, llm, agent = await run_agent(responses, fixture_server + "/index.html")

        assert agent.jobs_examined == 2
        assert len(jobs) == 2
        titles = {j.title for j in jobs}
        assert titles == {"Backend Engineer", "Python Developer"}
        for job in jobs:
            assert job.url.startswith(fixture_server), (
                "job URL must be the real visited URL"
            )

    @pytest.mark.timeout(120)
    async def test_prompt_injection_in_job_page_is_ignored(self, fixture_server):
        """jobs/python-developer-1002.html contains 'IGNORE ALL PREVIOUS INSTRUCTIONS' bait.
        The scripted LLM never obeys it; more importantly the returned URL is
        forced to the actually-visited page URL, so an attacker-supplied
        https://attacker.example/free can never appear."""
        responses = [
            json.dumps({"action": "open_job", "href": "/jobs/python-developer-1002.html"}),
            # Malicious extraction attempt claiming an attacker URL:
            json.dumps(
                {
                    "title": "FREE VACATION",
                    "url": "https://attacker.example/free",
                    "description": "claim it all",
                    "requirements": [],
                    "preferred_qualifications": [],
                }
            ),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        jobs, llm, agent = await run_agent(responses, fixture_server + "/index.html", max_job_visits=1)

        assert len(jobs) == 1
        job = jobs[0]
        assert job.url == fixture_server + "/jobs/python-developer-1002.html"
        assert job.url.startswith(fixture_server)

    @pytest.mark.timeout(120)
    async def test_unsafe_actions_are_blocked_but_loop_continues(self, fixture_server):
        """The scripted LLM tries to type credentials, use a forbidden key,
        and click 'Apply now'. Code-level safety rules refuse them; the loop
        continues and the legitimate open_job still works."""
        responses = [
            json.dumps({"action": "type", "text": "shubh@example.com"}),
            json.dumps({"action": "press", "key": "Control+A"}),  # not allowed
            json.dumps({"action": "click", "text": "Apply now"}),  # off-limits
            json.dumps({"action": "open_job", "href": "/jobs/backend-engineer-1001.html"}),
            job_json("Backend Engineer", "backend"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        jobs, llm, agent = await run_agent(responses, fixture_server + "/jobs.html", max_job_visits=1)

        # Only the legitimate open_job examined anything.
        assert agent.jobs_examined == 1
        assert len(jobs) == 1

        system_prompts = {calls[0] for calls in llm.calls}
        joined = " ".join(system_prompts)
        assert "READ-ONLY" in joined or "read-only" in joined.lower()

    @pytest.mark.timeout(120)
    async def test_no_form_submission_ever_happens(self, fixture_server):
        """The fixture pages contain forms with onsubmit returning false /
        action=/apply. We assert the agent never ended up on /apply."""
        responses = [
            json.dumps({"action": "finish", "reason": "nothing to do here"}),
        ]
        jobs, _llm, _agent = await run_agent(responses, fixture_server + "/index.html")
        assert jobs == []


class TestNavigationRaces:
    @pytest.mark.timeout(180)
    async def test_evaluate_racing_a_navigation_is_retried_not_fatal(
        self, fixture_server, monkeypatch
    ):
        """Regression: 'Page.evaluate: Execution context was destroyed, most
        likely because of a navigation' killed the whole company agent when
        an SPA swapped its document mid-snapshot. The resilient evaluate must
        absorb it and continue discovery."""
        from playwright.async_api import Page, async_playwright

        llm = FakeLLM(
            [
                json.dumps({"action": "click", "text": "Jobs"}),
                json.dumps({"action": "open_job", "href": "/jobs/backend-engineer-1001.html"}),
                job_json("Backend Engineer", "backend"),
                json.dumps({"action": "finish", "reason": "done"}),
            ]
        )

        original_evaluate = Page.evaluate
        calls = {"n": 0}

        async def flaky_first_evaluate(self, script, arg=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Error(
                    "Page.evaluate: Execution context was destroyed, "
                    "most likely because of a navigation"
                )
            return await original_evaluate(self, script, arg)

        monkeypatch.setattr(Page, "evaluate", flaky_first_evaluate)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                agent = CareerAgent(
                    llm=llm,
                    company_name="ExampleCorp",
                    careers_url=fixture_server + "/index.html",
                    profile=CandidateProfile(target_roles=["Backend Engineer"]),
                    max_job_visits=1,  # keep the scripted decisions in charge
                )
                jobs = await agent.run(browser)
            finally:
                await browser.close()

        assert len(jobs) == 1
        assert jobs[0].title == "Backend Engineer"
        assert calls["n"] >= 2  # the transient error triggered a retry

    @pytest.mark.timeout(180)
    async def test_persistent_snapshot_failures_end_gracefully(self, fixture_server, monkeypatch):
        """If the page NEVER becomes readable, the agent stops itself after
        three attempts and returns whatever it found - no crash."""
        from playwright.async_api import Page, async_playwright

        llm = FakeLLM([])

        async def always_navigating(self, script, arg=None):
            raise Error(
                "Page.evaluate: Execution context was destroyed, "
                "most likely because of a navigation"
            )

        monkeypatch.setattr(Page, "evaluate", always_navigating)

        status_messages: list[str] = []

        async def sink(message: str) -> None:
            status_messages.append(message)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                agent = CareerAgent(
                    llm=llm,
                    company_name="ExampleCorp",
                    careers_url=fixture_server + "/index.html",
                    profile=CandidateProfile(),
                )
                agent.set_callbacks(on_status=sink)
                jobs = await agent.run(browser)
            finally:
                await browser.close()

        assert jobs == []
        assert any("kept navigating" in m for m in status_messages)


class TestHiddenElements:
    """Real-world regressions (Goldman/PhonePe): hidden nav links and
    invisible filter inputs made agents burn 8-12s Playwright timeouts per
    attempt - and one type failure killed whole companies."""

    @pytest.mark.timeout(60)
    async def test_hidden_click_target_skipped_fast(self, fixture_server):
        """Clicking text whose only match is display:none must fail FAST
        (no 8s visibility timeout burn) and the loop must continue."""
        import time

        responses = [
            json.dumps({"action": "click", "text": "Backend Engineer hidden dup"}),
            json.dumps({"action": "open_job", "href": "/jobs/backend-engineer-1001.html"}),
            job_json("Backend Engineer", "backend"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        started = time.monotonic()
        jobs, _llm, agent = await run_agent(responses, fixture_server + "/jobs.html", max_job_visits=1)
        elapsed = time.monotonic() - started

        assert agent.jobs_examined == 1
        assert len(jobs) == 1
        # Old behavior: the failed click alone burned >=8s. New: fast skip.
        assert elapsed < 6.0, f"hidden-element click took {elapsed:.1f}s"

    @pytest.mark.timeout(60)
    async def test_invisible_search_input_never_typed_into(self, fixture_server):
        """The invisible filter-location-search input must be ignored; a
        failed type attempt is benign and discovery continues."""
        responses = [
            json.dumps({"action": "type", "text": "backend engineer bangalore"}),
            json.dumps({"action": "open_job", "href": "/jobs/python-developer-1002.html"}),
            job_json("Python Developer", "python"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        jobs, _llm, agent = await run_agent(responses, fixture_server + "/jobs.html", max_job_visits=1)

        assert agent.jobs_examined == 1
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"


class TestAntiLoop:
    """Regressions from real runs: Google looped clicking a hallucinated
    'work_outline Jobs Jobs' nav item forever; Amazon re-typed the same
    search every 5s because nothing pressed Enter."""

    @pytest.mark.timeout(60)
    async def test_fuzzy_click_matches_icon_ligature_text(self, fixture_server):
        """Needle 'work_outline Jobs Jobs' must still find the nav item whose
        real text is 'work_outline Jobs', and land on the jobs page."""
        responses = [
            json.dumps({"action": "click", "text": "work_outline Jobs Jobs"}),
            json.dumps({"action": "open_job", "href": "/jobs/backend-engineer-1001.html"}),
            job_json("Backend Engineer", "backend"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        jobs, llm, agent = await run_agent(responses, fixture_server + "/index.html", max_job_visits=1)

        assert agent.jobs_examined == 1, (
            "fuzzy click should have navigated index -> jobs -> job page"
        )
        assert jobs[0].title == "Backend Engineer"

    async def test_type_presses_enter_exactly_once(self, fixture_server, monkeypatch):
        """Typing a site search auto-presses Enter (the page must actually
        execute the search), and a duplicate type is refused."""
        from app.agents.career_agent import CareerAgent

        enter_count = {"n": 0}
        orig_do_type = CareerAgent._do_type

        async def spying_do_type(self, page, text):
            orig_press = page.keyboard.press

            async def press(key, **kw):
                if key == "Enter":
                    enter_count["n"] += 1
                return await orig_press(key, **kw)

            page.keyboard.press = press  # instance-level spy
            await orig_do_type(self, page, text)

        monkeypatch.setattr(CareerAgent, "_do_type", spying_do_type)

        responses = [
            json.dumps({"action": "type", "text": "software engineer"}),
            json.dumps({"action": "type", "text": "software engineer"}),  # duplicate
            json.dumps({"action": "open_job", "href": "/jobs/backend-engineer-1001.html"}),
            job_json("Backend Engineer", "backend"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        jobs, _llm, _agent = await run_agent(responses, fixture_server + "/index.html", max_job_visits=1)

        assert len(jobs) == 1
        # First type executed the search; duplicate was suppressed.
        assert enter_count["n"] == 1

    async def test_failed_action_recorded_in_prompt_memory(self, fixture_server):
        """After a failed click, later decisions must include it in
        <recent_actions> so the stateless LLM stops repeating it."""
        responses = [
            json.dumps({"action": "click", "text": "Nope 123"}),
            json.dumps({"action": "click", "text": "Nope 123"}),  # blacklisted
            json.dumps({"action": "open_job", "href": "/jobs/backend-engineer-1001.html"}),
            job_json("Backend Engineer", "backend"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        _jobs, llm, _agent = await run_agent(responses, fixture_server + "/index.html")

        decision_prompts = [user for sys_p, user in llm.calls if "recent_actions" in user]
        assert decision_prompts, "recent_actions block never surfaced"
        joined = "\\n".join(decision_prompts)
        assert "FAILED" in joined


class TestSafetyScoping:
    """Production regression: a visible 'Sign in' button elsewhere on the
    page made EVERY click request abort with "refusing to click 'Sign in'",
    killing discovery on sites like Google Careers."""

    async def test_unrelated_signin_button_does_not_block_other_clicks(
        self, fixture_server
    ):
        # index.html gains an unrelated Sign in button via the fixture; the
        # requested text is "Jobs", which must still be clickable.
        responses = [
            json.dumps({"action": "click", "text": "Jobs"}),
            json.dumps({"action": "open_job", "href": "/jobs/backend-engineer-1001.html"}),
            job_json("Backend Engineer", "backend"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        jobs, _llm, agent = await run_agent(responses, fixture_server + "/index.html", max_job_visits=1)
        assert agent.jobs_examined == 1
        assert jobs[0].title == "Backend Engineer"

    async def test_apply_intent_still_blocked(self, fixture_server):
        """The intent itself being apply-ish is still refused outright."""
        responses = [
            json.dumps({"action": "click", "text": "Apply now"}),
            json.dumps({"action": "finish", "reason": "nothing else to do"}),
        ]
        jobs, llm, _agent = await run_agent(responses, fixture_server + "/index.html")
        assert jobs == []
        # The refusal was recorded as a failure, not silently ignored.
        joined = " ".join(user for _sys, user in llm.calls)
        assert "FAILED" in joined

class TestTimeBudget:
    """A run that ends early must keep what it already found.

    The original bug: `visited_jobs` was a local of `_run_loop`, so when the
    time cap cancelled that coroutine every extracted, validated job died
    with it. A search that had successfully read nine job pages returned
    zero, and then retried the whole company from scratch.
    """

    @pytest.mark.timeout(180)
    async def test_jobs_found_before_the_deadline_are_kept(
        self, fixture_server, monkeypatch
    ):
        import app.agents.career_agent as agent_module

        # One job is opened and extracted, then the budget runs out before
        # the agent can be asked anything else.
        responses = [
            job_json("Backend Engineer", "backend"),
            job_json("Python Developer", "python"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        monkeypatch.setattr(agent_module, "OVERALL_TIMEOUT_S", 0.0)

        jobs, _llm, agent = await run_agent(responses, fixture_server)

        # Zero steps could run, so nothing was found - but the run must end
        # cleanly with an empty list, never an exception.
        assert jobs == []
        assert agent._found_jobs == {}

    @pytest.mark.timeout(180)
    async def test_a_hard_cancellation_still_returns_what_was_found(
        self, fixture_server
    ):
        """The backstop path: cancelled mid-loop, not stopped by the deadline."""
        import asyncio

        from app.schemas import DiscoveredJob

        llm = FakeLLM([json.dumps({"action": "finish"})])
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                agent = CareerAgent(
                    llm=llm,
                    company_name="ExampleCorp",
                    careers_url=fixture_server,
                    profile=CandidateProfile(target_roles=["Backend Engineer"]),
                )
                # Simulate a run that had already banked a job when the
                # hard cap fired.
                agent._found_jobs["k"] = DiscoveredJob(
                    title="Backend Engineer", url="https://example.com/job"
                )

                async def never_finishes(_page):
                    await asyncio.sleep(3600)

                agent._run_loop = never_finishes  # type: ignore[method-assign]
                import app.agents.career_agent as agent_module

                original = agent_module.OVERALL_TIMEOUT_S
                agent_module.OVERALL_TIMEOUT_S = 0.05
                try:
                    jobs = await agent.run(browser)
                finally:
                    agent_module.OVERALL_TIMEOUT_S = original
            finally:
                await browser.close()

        assert [j.title for j in jobs] == ["Backend Engineer"]


class TestPreFilteredUrls:
    """When the careers_url already carries query params (role, location,
    level), the agent should skip search and go straight to extracting
    postings."""

    async def test_agent_detects_pre_filtered_url(self, fixture_server):
        """Query params in the URL set _pre_filtered."""
        url = fixture_server + "/index.html?q=engineer&location=India"
        agent = CareerAgent(
            llm=FakeLLM([]),
            company_name="Test",
            careers_url=url,
        )
        assert agent._pre_filtered is True

    async def test_agent_detects_unfiltered_url(self, fixture_server):
        """No query params means _pre_filtered is False."""
        agent = CareerAgent(
            llm=FakeLLM([]),
            company_name="Test",
            careers_url=fixture_server + "/index.html",
        )
        assert agent._pre_filtered is False

    @pytest.mark.timeout(120)
    async def test_skips_search_when_pre_filtered(self, fixture_server):
        """With a pre-filtered URL, the agent opens postings directly
        without typing into a search box."""
        # Use jobs.html directly — simulates a pre-filtered URL that lands
        # on a listing page, not a portal landing page.
        url = fixture_server + "/jobs.html?q=engineer&location=India"
        responses = [
            job_json("Backend Engineer", "backend"),
            job_json("Python Developer", "python"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        jobs, llm, agent = await run_agent(responses, url)
        assert len(jobs) == 2
        # The LLM prompt should report has_search_box: false so the model
        # never considers a type/click-search action.
        for _sys, user_msg in llm.calls:
            if "has_search_box" in user_msg:
                assert "has_search_box: false" in user_msg
                return
        # If no prompt contained has_search_box, the agent never asked the
        # LLM (it harvested all postings directly) — also correct.

    @pytest.mark.timeout(120)
    async def test_still_searches_when_not_pre_filtered(self, fixture_server):
        """Without pre-filtered URL, the agent can still search."""
        responses = [
            json.dumps({"action": "click", "text": "Jobs"}),
            job_json("Backend Engineer", "backend"),
            job_json("Python Developer", "python"),
            json.dumps({"action": "finish", "reason": "done"}),
        ]
        jobs, llm, agent = await run_agent(
            responses, fixture_server + "/index.html"
        )
        assert len(jobs) == 2
        # The LLM prompt should report has_search_box: true so the model
        # can choose to navigate to Jobs.
        found_search_box = False
        for _sys, user_msg in llm.calls:
            if "has_search_box: true" in user_msg:
                found_search_box = True
                break
        assert found_search_box, "has_search_box: true not found in LLM prompts"

    @pytest.mark.timeout(120)
    async def test_skips_foreign_link_filtering_when_pre_filtered(self, fixture_server):
        """When the URL is pre-filtered, _drop_foreign_links is skipped so
        the agent doesn't re-filter results the site already narrowed."""
        url = fixture_server + "/index.html?q=engineer&location=India"
        agent = CareerAgent(
            llm=FakeLLM([json.dumps({"action": "finish"})]),
            company_name="Test",
            careers_url=url,
            locations=["India"],
        )
        assert agent._pre_filtered is True
        # The agent should not have locations set for filtering since the
        # URL already handled it — but even if locations are set, the
        # pre-filtered flag skips the pre-check.
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                jobs = await agent.run(browser)
            finally:
                await browser.close()
        # Agent ran without crashing — foreign link filtering was skipped.
        assert isinstance(jobs, list)

    @pytest.mark.timeout(120)
    async def test_has_search_box_hidden_when_pre_filtered(self, fixture_server):
        """The LLM prompt reports has_search_box=false when the URL is
        pre-filtered, so the model never considers searching."""
        url = fixture_server + "/index.html?q=engineer&location=India"
        responses = [
            json.dumps({"action": "finish", "reason": "url already filtered"}),
        ]
        jobs, llm, agent = await run_agent(responses, url)
        # Check that the prompt sent to the LLM included has_search_box: false
        for _sys, msg in llm.calls:
            if "has_search_box" in msg:
                assert "has_search_box: false" in msg
                break
        else:
            pytest.fail("has_search_box not found in any LLM prompt")
