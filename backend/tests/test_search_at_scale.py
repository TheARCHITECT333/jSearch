"""What a long company list does to a search.

At one LLM slot the work is serial, so a long list takes hours. Two things
used to make that catastrophic rather than merely slow:

  1. `record.results` was assigned ONCE, after every company had been browsed
     AND matched. A search stopped at minute 113 of its 114-minute budget
     returned nothing, however much it had found.
  2. The budget was sized on browser slots (`ceil(n/4)` rounds), which
     assumes four companies progress at once. With a serial model they do
     not, so the budget was ~20% short of the work and the search was killed
     just before finishing.
"""

import asyncio

import pytest

from app.services import search as search_module
from app.schemas import CompanyInput, JobResult, MatchResult


def _record(names, **kw):
    companies = [
        CompanyInput(name=n, careers_url=f"https://{n.lower()}.example/jobs")
        for n in names
    ]
    return search_module._SearchRecord("s1", companies, **kw)


def _result(company: str, title: str) -> JobResult:
    return JobResult(
        company=company,
        job_title=title,
        job_url=f"https://{company.lower()}.example/{title}",
        match=MatchResult(
            overall_score=70, role_fit=70, skill_fit=70,
            experience_fit=70, location_fit=70,
        ),
    )


class TestDeadline:
    def test_a_fresh_record_has_no_deadline(self):
        # Queued time must not count: a search sitting behind another one
        # should not start already out of budget.
        assert _record(["A"]).out_of_time() is False

    def test_out_of_time_once_the_deadline_passes(self):
        import time

        record = _record(["A"])
        record.deadline = time.monotonic() - 1
        assert record.out_of_time() is True

    def test_still_in_time_before_the_deadline(self):
        import time

        record = _record(["A"])
        record.deadline = time.monotonic() + 60
        assert record.out_of_time() is False


class TestPartialResultsSurvive:
    """Results published per company, so time pressure costs you the
    companies not reached - not the ones that finished."""

    def test_results_accumulate_as_companies_finish(self):
        record = _record(["Google", "Amazon"])
        record.results.extend([_result("Google", "SWE")])
        assert [r.company for r in record.snapshot().results] == ["Google"]

        record.results.extend([_result("Amazon", "SDE")])
        assert len(record.snapshot().results) == 2

    async def test_a_company_arriving_out_of_time_is_skipped_not_run(self):
        import time

        manager = search_module.SearchManager()
        record = _record(["Google"])
        record.deadline = time.monotonic() - 1

        called = False

        async def should_not_run(*a, **k):
            nonlocal called
            called = True
            return []

        manager._browse_with_retry = should_not_run  # type: ignore[method-assign]
        jobs = await manager._run_company(record, None, record.companies[0], None, None)

        assert jobs == []
        assert called is False, "a company with no budget left must not browse"
        assert record.skipped_companies == 1
        assert record.progress["Google"].status == "failed"
        assert "ran out of time" in (record.progress["Google"].message or "").lower()

    async def test_skipping_leaves_earlier_results_intact(self):
        import time

        manager = search_module.SearchManager()
        record = _record(["Google", "Amazon"])
        record.results.append(_result("Google", "SWE"))
        record.deadline = time.monotonic() - 1

        await manager._run_company(record, None, record.companies[1], None, None)

        # The whole point: Amazon is skipped, Google's work is not discarded.
        assert [r.company for r in record.snapshot().results] == ["Google"]


class TestBudgetTracksTheRealBottleneck:
    def test_fifty_companies_get_a_budget_that_fits_serial_work(self, monkeypatch):
        from app.llm import base as llm_base

        monkeypatch.setattr(llm_base, "LLM_CONCURRENCY", 1)
        budget = search_module.search_budget_seconds(50, floor_s=0, concurrency=4)

        # Measured: ~24 LLM calls per company at ~7s. The budget must cover
        # that, or the search is killed before it can finish.
        estimated_work = 50 * 24 * 7.0
        assert budget > estimated_work
