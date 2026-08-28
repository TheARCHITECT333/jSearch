"""In-process search execution.

Searches are JOBS: the API enqueues them and a bounded pool of async runner
tasks executes them (queue + runners live in this process's event loop - no
external broker, nothing persisted). A restart loses active searches,
which is acceptable since the frontend owns completed results.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from typing import NamedTuple
from urllib.parse import urlparse

from ..llm import LLM, LLMError
from ..matching.matcher import match_job
from ..schemas import (
    CandidateProfile,
    CompanyInput,
    CompanyProgress,
    JobResult,
    LLMConfig,
    MatchResult,
    SearchStatus,
)
from ..logging_setup import company_context, search_context
from . import store
from .dedup import deduplicate_jobs, normalize_job_url
from .discovery import discover_company_jobs
from .resume import extract_profile

logger = logging.getLogger(__name__)

MATCH_CONCURRENCY = 3
# Jobs matched within this window are NOT re-matched; their stored scores
# are reused instead - don't waste LLM time on jobs already evaluated.
SEEN_JOB_TTL_DAYS = float(os.getenv("SEEN_JOB_TTL_DAYS", "7"))

# --- Reliability knobs ----------------------------------------------------
# Companies explored SIMULTANEOUSLY per search (Chromium contexts are heavy).
COMPANY_CONCURRENCY = max(1, int(os.getenv("COMPANY_CONCURRENCY", "4")))
# Floor for the whole-search budget; a stuck search must not hold a runner
# forever. The effective budget also scales with the company count - see
# `search_budget_seconds`.
SEARCH_TIMEOUT_S = float(os.getenv("SEARCH_TIMEOUT_S", "1800"))
# Discovery attempts per company (1 try + 1 retry by default).
DISCOVERY_ATTEMPTS = max(1, int(os.getenv("DISCOVERY_ATTEMPTS", "2")))
DISCOVERY_RETRY_BACKOFF_S = float(os.getenv("DISCOVERY_RETRY_BACKOFF_S", "2"))


def search_budget_seconds(
    company_count: int,
    *,
    floor_s: float | None = None,
    concurrency: int | None = None,
) -> float:
    """Time budget for a whole search, derived from how much work it is.

    A fixed timeout silently becomes wrong the moment the company list
    grows: 43 companies at COMPANY_CONCURRENCY=4 need ~11 sequential
    rounds, which no constant can anticipate. So the budget is
    `rounds * per-company cap`, floored at SEARCH_TIMEOUT_S and padded for
    the matching phase that follows discovery.
    """
    from ..agents.career_agent import OVERALL_TIMEOUT_S as PER_COMPANY_CAP_S
    from ..llm.base import LLM_CONCURRENCY

    floor = SEARCH_TIMEOUT_S if floor_s is None else floor_s
    slots = COMPANY_CONCURRENCY if concurrency is None else concurrency
    # Browser slots are not the real limit when the model answers one call at
    # a time: four companies can browse at once, but only one can think, so
    # they finish about as slowly as if they had run one after another.
    # Sizing the budget on browser slots alone granted 114 minutes for 140
    # minutes of work, and the search was killed just short of the end.
    slots = max(1, min(slots, LLM_CONCURRENCY))
    rounds = max(1, -(-max(0, company_count) // slots))  # ceil division
    # x1.25 leaves room for the matching each company does as it finishes.
    return max(floor, rounds * PER_COMPANY_CAP_S * 1.25)


def _causes(error: BaseException):
    """The exception and everything it was raised from.

    `discovery.py` rewraps every failure as a CareerAgentError, so the only
    place the real cause survives is the `raise ... from exc` chain. Classify
    on TYPE from that chain, never on the message text: "site unreachable"
    and "model unreachable" read almost identically and mean opposite things.
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__


def _blames_the_model(error: BaseException) -> bool:
    from ..llm import LLMAvailabilityError, LLMError
    from ..agents.career_agent import CareerAgentError

    return any(
        isinstance(cause, (LLMAvailabilityError,))
        or (isinstance(cause, LLMError) and not isinstance(cause, CareerAgentError))
        for cause in _causes(error)
    )


def _out_of_time(error: BaseException) -> bool:
    return any(isinstance(cause, asyncio.TimeoutError) for cause in _causes(error))


def _is_retryable(error: BaseException) -> bool:
    """Is another full attempt at this company worth the time it costs?

    Not for a timeout, and not when the model itself is the problem: the
    second attempt hits the same slow server with the same budget and no
    memory of what it already saw, so it burns another full budget to reach
    the same place. A flaky page load, on the other hand, is worth one retry.
    """
    return not (_out_of_time(error) or _blames_the_model(error))


def _failure_message(error: BaseException) -> str:
    """What to show the user for a company that did not finish.

    "Career site could not be navigated" used to be shown for every failure,
    including a run that browsed the site perfectly well for six minutes and
    then ran out of budget. Saying the wrong thing sends people to debug the
    wrong problem.
    """
    if _out_of_time(error):
        return "Ran out of time on this site before anything could be kept."
    if _blames_the_model(error):
        return "The model did not answer while browsing this site."
    return "Career site could not be navigated."


class SearchQueueFullError(Exception):
    """Raised when the in-process job queue is at capacity."""


class _SearchJob(NamedTuple):
    record: _SearchRecord
    resume_latex: str
    llm_config: LLMConfig
    llm_factory: object


@contextlib.asynccontextmanager
async def chromium_browser():
    """Launch a real headless Chromium (used in production)."""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            await browser.close()


class SearchNotFoundError(KeyError):
    pass


def _site_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme or 'https'}://{parsed.netloc}"


def _result_from_history(
    company: CompanyInput, job, match_row
) -> JobResult:
    """Rebuild a JobResult from a stored MatchRow (no LLM call spent)."""
    from ..models import Match as MatchRow

    assert isinstance(match_row, MatchRow)
    return JobResult(
        company=company.name,
        company_url=_site_origin(company.careers_url),
        careers_url=company.careers_url,
        job_title=job.title,
        job_url=job.url,
        location=job.location,
        employment_type=job.employment_type,
        description=job.description,
        requirements=list(job.requirements),
        preferred_qualifications=list(job.preferred_qualifications),
        match=MatchResult(
            overall_score=match_row.overall_score,
            role_fit=match_row.role_fit,
            skill_fit=match_row.skill_fit,
            experience_fit=match_row.experience_fit,
            location_fit=match_row.location_fit,
            matching_skills=list(match_row.matching_skills_json or []),
            missing_skills=list(match_row.missing_skills_json or []),
            reason=match_row.reason,
            disqualifiers=list(match_row.disqualifiers_json or []),
            seniority_band=match_row.seniority_band,
            required_years=match_row.required_years,
            keyword_coverage=match_row.keyword_coverage or 0,
            missing_keywords=list(match_row.missing_keywords_json or []),
        ),
    )


def _rank_key(result: JobResult) -> tuple:
    """Ranked jobs first, best fit first within each group.

    Disqualified jobs are not scored down, they are moved out: a stated hard
    bar you fail is not "85 minus a bit", it is a different list.
    """
    return (not result.match.disqualified, result.match.overall_score)


class _SearchRecord:
    def __init__(
        self,
        search_id: str,
        companies: list[CompanyInput],
        freshness: str = "any",
        locations: list[str] | None = None,
    ) -> None:
        self.id = search_id
        self.status: str = "queued"
        self.companies: list[CompanyInput] = companies
        self.freshness = freshness
        self.locations = locations or []
        self.progress: dict[str, CompanyProgress] = {
            c.name: CompanyProgress(company=c.name, status="pending") for c in companies
        }
        self.results: list[JobResult] = []
        self.error: str | None = None
        self.created_at = time.time()
        # Wall-clock point past which no new company is started. Set once the
        # search actually begins running, not when it is queued.
        self.deadline: float | None = None
        self.skipped_companies = 0

    def out_of_time(self) -> bool:
        """True once there is no budget left to start new work.

        Deliberately checked BEFORE starting a company or a match rather
        than relied on from outside: the outer wait_for cancels the search
        outright, and a cancelled search reports nothing.
        """
        return self.deadline is not None and time.monotonic() >= self.deadline

    def snapshot(self) -> SearchStatus:
        return SearchStatus(
            id=self.id,
            status=self.status,  # type: ignore[arg-type]
            companies=list(self.progress.values()),
            results=sorted(self.results, key=_rank_key, reverse=True),
            error=self.error,
        )


class SearchManager:
    """Owns all active searches. Single-process, single-event-loop.

    Execution model: `start_search` enqueues a job; up to
    `max_concurrent_searches` runner tasks drain the queue concurrently
    (each runner handles one search at a time). Runners terminate as soon
    as the queue is empty - no idle loops, no external infrastructure.
    """

    def __init__(
        self,
        browser_factory=chromium_browser,
        *,
        max_concurrent_searches: int = 2,
        queue_max_size: int = 50,
        company_concurrency: int | None = None,
        context_gate=None,
        search_timeout_s: float | None = None,
    ) -> None:
        self._searches: dict[str, _SearchRecord] = {}
        self._browser_factory = browser_factory
        self._max_concurrent = max(1, max_concurrent_searches)
        # Scheduler: companies of ONE search browsing at once.
        self._company_concurrency = max(
            1,
            company_concurrency if company_concurrency is not None else COMPANY_CONCURRENCY,
        )
        self._company_slots = asyncio.Semaphore(self._company_concurrency)
        # Global Chromium-context cap across all searches (RAM guard).
        from .browser_pool import global_context_gate

        self._context_gate = context_gate if context_gate is not None else global_context_gate
        # None = derive the budget per search from the company count.
        self._search_timeout_override = search_timeout_s
        self._queue: asyncio.Queue[_SearchJob | None] = asyncio.Queue(
            maxsize=max(1, queue_max_size)
        )
        self._active_runners = 0
        self._runners: set[asyncio.Task] = set()
        # Per-search cancellation.
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._job_tasks: dict[str, asyncio.Task] = {}

    # -- API ------------------------------------------------------------------

    def start_search(
        self,
        *,
        resume_latex: str,
        companies: list[CompanyInput],
        llm_config: LLMConfig,
        llm_factory,
        freshness: str = "any",
        locations: list[str] | None = None,
    ) -> str:
        """Enqueue a search job. `llm_factory(config) -> LLM` is injected so
        tests can substitute it. Raises SearchQueueFullError under pressure."""
        search_id = uuid.uuid4().hex[:12]
        record = _SearchRecord(search_id, companies, freshness, locations)
        self._searches[search_id] = record
        self._cancel_events[search_id] = asyncio.Event()

        job = _SearchJob(
            record=record,
            resume_latex=resume_latex,
            llm_config=llm_config,
            llm_factory=llm_factory,
        )
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            self._searches.pop(search_id, None)
            raise SearchQueueFullError(
                "Too many searches are queued right now. Try again shortly."
            ) from None
        self._ensure_runner()
        return search_id

    def get_status(self, search_id: str) -> SearchStatus:
        record = self._searches.get(search_id)
        if record is None:
            raise SearchNotFoundError(search_id)
        return record.snapshot()

    def cancel_search(self, search_id: str) -> bool:
        """Cancel a queued or running search. Returns False when the search
        is unknown or already terminal."""
        record = self._searches.get(search_id)
        if record is None:
            return False
        if record.status in ("completed", "failed", "cancelled"):
            return False
        event = self._cancel_events.get(search_id)
        if event is not None:
            event.set()
        if record.status == "queued":
            record.status = "cancelled"
            record.error = "Cancelled by user."
        return True

    def _is_cancelled(self, search_id: str) -> bool:
        event = self._cancel_events.get(search_id)
        return bool(event is not None and event.is_set())

    async def drain(self, timeout: float = 5.0) -> None:
        """Best-effort graceful shutdown: wait briefly for queued/in-flight
        work, then cancel whatever is still running."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and self._has_pending_work():
            await asyncio.sleep(0.05)
        for task in list(self._runners):
            if not task.done():
                task.cancel()
        if self._runners:
            await asyncio.gather(*self._runners, return_exceptions=True)

    def _has_pending_work(self) -> bool:
        return not self._queue.empty() or self._active_runners > 0

    # -- worker pool -------------------------------------------------------------

    def _ensure_runner(self) -> None:
        """Spawn a runner if capacity allows and there is queued work."""
        if self._queue.empty():
            return
        if self._active_runners >= self._max_concurrent:
            return
        self._active_runners += 1
        runner = asyncio.create_task(self._runner_loop())
        self._runners.add(runner)
        runner.add_done_callback(self._on_runner_done)

    def _on_runner_done(self, task: asyncio.Task) -> None:
        self._runners.discard(task)

    async def _runner_loop(self) -> None:
        """Drain jobs until the queue is empty, then exit."""
        try:
            while True:
                try:
                    job = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    if job.record.status == "cancelled":
                        continue  # cancelled while still queued
                    await self._run_tracked(job)
                except Exception:  # noqa: BLE001 - one bad job never kills the runner
                    logger.exception("runner crashed processing search %s", job.record.id)
                    job.record.status = "failed"
                    job.record.error = "The search failed unexpectedly. Check the backend logs."
                finally:
                    self._queue.task_done()
        finally:
            self._active_runners -= 1
            if not self._queue.empty():
                self._ensure_runner()

    async def _run_tracked(self, job: _SearchJob) -> None:
        """Run one search as its own task so it can be timed out or
        cancelled without killing the runner loop."""
        record = job.record
        budget_s = self._budget_for(record)
        with search_context(record.id):
            # Timeout lives INSIDE the task: wait_for cancels the search on
            # expiry and TimeoutError surfaces here for reporting.
            task = asyncio.create_task(
                asyncio.wait_for(self._process(job), timeout=budget_s)
            )
            self._job_tasks[record.id] = task
            cancel_wait = asyncio.ensure_future(self._wait_cancel(record.id))
            try:
                done, _pending = await asyncio.wait(
                    {task, cancel_wait}, return_when=asyncio.FIRST_COMPLETED
                )
                if cancel_wait in done and not task.done():
                    record.status = "cancelled"
                    record.error = "Cancelled by user."
                    logger.info(
                        "cancelled by user", extra={"event": "search.cancelled"}
                    )
                    task.cancel()
                try:
                    await task
                except asyncio.TimeoutError:
                    record.status = "failed"
                    record.error = (
                        f"The search exceeded its {budget_s:.0f}s time budget "
                        "and was stopped."
                    )
                    logger.warning(
                        "exceeded its %.0fs time budget",
                        budget_s,
                        extra={"event": "search.timeout", "budget_s": round(budget_s)},
                    )
                except asyncio.CancelledError:
                    if record.status != "cancelled":
                        raise
                except Exception:  # noqa: BLE001
                    logger.exception("runner crashed processing search")
                    record.status = "failed"
                    record.error = "The search failed unexpectedly. Check the backend logs."
            finally:
                cancel_wait.cancel()
                self._job_tasks.pop(record.id, None)

    def _budget_for(self, record: _SearchRecord) -> float:
        """Explicit override wins (tests); otherwise scale with the work."""
        if self._search_timeout_override is not None:
            return self._search_timeout_override
        return search_budget_seconds(
            len(record.companies), concurrency=self._company_concurrency
        )

    async def _wait_cancel(self, search_id: str) -> None:
        event = self._cancel_events.get(search_id)
        if event is not None:
            await event.wait()

    async def _process(self, job: _SearchJob) -> None:
        await self._execute(
            job.record,
            job.resume_latex,
            job.llm_config,
            job.llm_factory,
        )

    def prune_old(self, max_age_seconds: float = 3600 * 6) -> None:
        cutoff = time.time() - max_age_seconds
        stale = [sid for sid, rec in self._searches.items() if rec.created_at < cutoff]
        for sid in stale:
            self._searches.pop(sid, None)

    # -- execution -------------------------------------------------------------

    async def _execute(
        self,
        record: _SearchRecord,
        resume_latex: str,
        llm_config: LLMConfig,
        llm_factory,
    ) -> None:
        """Owns the full search lifecycle, INCLUDING the LLM client lifetime:
        the client must stay open until matching has finished.

        Everything below runs inside `search_context`, so every log line from
        the agents, matcher and store carries this search's id - two searches
        running at once stay tellable apart.
        """
        with search_context(record.id):
            record.status = "running"  # picked up by a runner
            started_at = time.monotonic()
            logger.info(
                "search started: %d company(ies), freshness=%s, locations=%s",
                len(record.companies),
                record.freshness,
                record.locations or "any",
                extra={
                    "event": "search.started",
                    "companies": len(record.companies),
                    "freshness": record.freshness,
                },
            )
            await store.record_search_started(
                record.id,
                [(c.name, c.careers_url) for c in record.companies],
                record.freshness,
                record.locations,
            )
            llm: LLM | None = None
            try:
                try:
                    llm = llm_factory(llm_config)
                except Exception as exc:  # noqa: BLE001 - bad config from UI
                    record.status = "failed"
                    record.error = f"Could not configure the LLM. {exc}"
                    logger.error("llm configuration failed: %s", exc)
                    return
                await self._execute_inner(record, resume_latex, llm, llm_config)
            except Exception:  # noqa: BLE001 - a search must never strand "running"
                logger.exception("search crashed")
                record.status = "failed"
                record.error = "The search failed unexpectedly. Check the backend logs."
            finally:
                if llm is not None:
                    await llm.close()
                await store.record_search_finished(record.snapshot())
                logger.info(
                    "search finished: %s in %.1fs, %d result(s)",
                    record.status,
                    time.monotonic() - started_at,
                    len(record.results),
                    extra={
                        "event": "search.finished",
                        "outcome": record.status,
                        "duration_s": round(time.monotonic() - started_at, 1),
                        "results": len(record.results),
                    },
                )

    async def _execute_inner(
        self,
        record: _SearchRecord,
        resume_latex: str,
        llm: LLM,
        llm_config: LLMConfig,
    ) -> None:
        # 1. Candidate profile (shared by every agent and the matcher).
        # Cached by resume-content hash: re-uploading the same .tex skips
        # the extraction LLM call entirely.
        try:
            profile, _cached = await store.extract_profile_cached(
                llm, resume_latex, llm_config
            )
        except LLMError as exc:
            record.status = "failed"
            record.error = f"Could not analyze your resume. {exc}"
            logger.error("profile extraction failed: %s", exc)
            return

        # Stop starting new companies at 85% of the budget, leaving room for
        # the ones already running to finish and publish. The outer wait_for
        # stays as a backstop, but should no longer be what ends a search.
        budget = self._budget_for(record)
        record.deadline = time.monotonic() + budget * 0.85

        # 2. Discovery AND matching per company, concurrently.
        #
        # These used to be two phases: browse all 50 companies, then match
        # everything. At one LLM slot that meant ~2 hours of discovery before
        # a single result existed, and `record.results` was assigned once at
        # the very end - so a search stopped at minute 113 of its 114-minute
        # budget returned nothing at all, however much it had found.
        #
        # Publishing per company means the results list only ever grows, the
        # UI fills in as sites finish, and running out of time costs you the
        # companies not yet reached rather than the whole run.
        seen_urls: set[str] = set()
        match_slots = asyncio.Semaphore(MATCH_CONCURRENCY)

        async with self._browser_factory() as browser:
            gathered = await asyncio.gather(
                *[
                    self._run_company(
                        record,
                        llm,
                        company,
                        profile,
                        browser,
                        resume_latex=resume_latex,
                        seen_urls=seen_urls,
                        match_slots=match_slots,
                    )
                    for company in record.companies
                ],
                return_exceptions=True,
            )

        failed_companies = 0
        for company, outcome in zip(record.companies, gathered):
            if isinstance(outcome, BaseException):
                failed_companies += 1
                progress = record.progress[company.name]
                progress.status = "failed"
                progress.message = _failure_message(outcome)
                logger.warning(
                    "company %s failed: %s",
                    company.name,
                    outcome,
                    extra={"event": "company.failed", "company": company.name},
                )

        if failed_companies == len(record.companies):
            record.status = "failed"
            record.error = "No career site could be searched successfully."
            return

        if record.skipped_companies:
            record.error = (
                f"Ran out of time before {record.skipped_companies} of "
                f"{len(record.companies)} companies could be searched. "
                "The results below are from the ones that finished."
            )

        ruled_out = sum(1 for r in record.results if r.match.disqualified)
        if ruled_out:
            logger.info(
                "%d of %d job(s) ruled out by a stated hard requirement",
                ruled_out,
                len(record.results),
                extra={"event": "match.ruled_out", "ruled_out": ruled_out},
            )
        record.status = "completed"

    async def _run_company(
        self,
        record: _SearchRecord,
        llm: LLM,
        company: CompanyInput,
        profile: CandidateProfile,
        browser,
        *,
        resume_latex: str = "",
        seen_urls: set[str] | None = None,
        match_slots: asyncio.Semaphore | None = None,
    ):
        """One company end to end: browse, filter, match, publish.

        Failures propagate - the caller isolates them.
        """
        with company_context(company.name):
            progress = record.progress[company.name]

            if self._is_cancelled(record.id):
                raise asyncio.CancelledError()

            # Every company waits its turn at the browser slots and then at
            # the LLM, so the ones at the back of a long list can arrive with
            # no budget left. Skipping them cheaply - and saying so - beats
            # starting work that will be cut off, and beats the outer
            # timeout killing the search and discarding what finished.
            if record.out_of_time():
                record.skipped_companies += 1
                progress.status = "failed"
                progress.message = "Skipped - the search ran out of time."
                logger.info(
                    "skipping %s: no budget left",
                    company.name,
                    extra={"event": "company.skipped", "company": company.name},
                )
                return []

            progress.status = "pending"
            progress.message = "Waiting for a browser slot..."

            waiting_since = time.monotonic()
            async with self._company_slots:
                waited = time.monotonic() - waiting_since
                if waited > 1.0:
                    logger.info(
                        "waited %.1fs for a browser slot",
                        waited,
                        extra={"event": "company.slot_wait", "waited_s": round(waited, 1)},
                    )
                if self._is_cancelled(record.id):
                    raise asyncio.CancelledError()
                jobs = await self._browse_with_retry(
                    record, llm, company, profile, browser, progress
                )

            # Browser slot released before matching: matching needs the LLM,
            # not Chromium, and holding a context through it would starve the
            # companies still waiting to browse.
            await self._publish_company(
                record,
                llm,
                company,
                profile,
                jobs,
                progress,
                resume_latex=resume_latex,
                seen_urls=seen_urls if seen_urls is not None else set(),
                match_slots=match_slots or asyncio.Semaphore(MATCH_CONCURRENCY),
            )
            return jobs

    async def _publish_company(
        self,
        record: _SearchRecord,
        llm: LLM,
        company: CompanyInput,
        profile: CandidateProfile,
        jobs,
        progress: CompanyProgress,
        *,
        resume_latex: str,
        seen_urls: set[str],
        match_slots: asyncio.Semaphore,
    ) -> None:
        """Filter, score and publish ONE company's jobs into record.results.

        Runs as soon as that company finishes browsing, so results appear
        while the rest of the list is still being worked through.
        """
        from .freshness import FRESHNESS_LABELS, filter_fresh_jobs
        from .locations import filter_jobs_by_location

        # 1. Drop provably-stale postings and clear location mismatches
        #    BEFORE spending any LLM call on matching. Jobs with no visible
        #    posting date / location are always kept (never guessed).
        fresh, stale = filter_fresh_jobs(jobs, record.freshness)
        in_location, elsewhere = filter_jobs_by_location(fresh, record.locations)

        notes: list[str] = []
        if stale:
            label = FRESHNESS_LABELS.get(record.freshness, "any age")
            notes.append(f"{len(stale)} listing(s) older than {label} skipped")
            logger.info(
                "skipped %d listing(s) older than %s",
                len(stale),
                label,
                extra={"event": "filter.stale", "skipped": len(stale)},
            )
        if elsewhere:
            wanted = ", ".join(record.locations) if record.locations else ""
            notes.append(f"{len(elsewhere)} listing(s) outside [{wanted}] skipped")
            logger.info(
                "skipped %d listing(s) outside target locations %s",
                len(elsewhere),
                record.locations,
                extra={"event": "filter.location", "skipped": len(elsewhere)},
            )

        # 2. Deduplicate within this company and against every company that
        #    has already published - the same posting is often listed twice.
        mine: list = []
        for job in deduplicate_jobs(in_location):
            key = normalize_job_url(job.url)
            if key in seen_urls:
                continue
            seen_urls.add(key)
            mine.append(job)

        progress.jobs_found = len(mine)
        if notes:
            progress.message = " · ".join(notes)

        if not mine:
            return

        # 3. Reuse history: jobs matched within SEEN_JOB_TTL_DAYS keep their
        #    stored scores - no LLM calls spent on them again.
        try:
            recent_rows = await store.find_recently_matched(
                mine, ttl_days=SEEN_JOB_TTL_DAYS
            )
        except Exception:  # noqa: BLE001 - history is best-effort
            logger.warning("recent-match lookup failed", exc_info=True)
            recent_rows = {}

        reused: list[JobResult] = []
        to_match: list = []
        for job in mine:
            stored_match_row = recent_rows.get(store.url_hash(job.url))
            if stored_match_row is None:
                to_match.append(job)
            else:
                reused.append(_result_from_history(company, job, stored_match_row))

        logger.info(
            "matching %d new job(s), %d reused",
            len(to_match),
            len(reused),
            extra={
                "event": "match.started",
                "to_match": len(to_match),
                "reused": len(reused),
            },
        )

        matched: list[JobResult] = []

        async def match_one(job) -> None:
            async with match_slots:
                if record.out_of_time():
                    return
                try:
                    match = await match_job(
                        llm,
                        profile,
                        job,
                        locations=record.locations or None,
                        resume_latex=resume_latex,
                    )
                except LLMError as exc:
                    logger.warning(
                        "match failed for %r: %s",
                        job.title,
                        exc,
                        extra={"event": "match.failed"},
                    )
                    return
                matched.append(
                    JobResult(
                        company=company.name,
                        company_url=_site_origin(company.careers_url),
                        careers_url=company.careers_url,
                        job_title=job.title,
                        job_url=job.url,
                        location=job.location,
                        employment_type=job.employment_type,
                        description=job.description,
                        requirements=job.requirements,
                        preferred_qualifications=job.preferred_qualifications,
                        match=match,
                    )
                )

        await asyncio.gather(*(match_one(job) for job in to_match))

        # 4. Publish. `record.results` only ever grows, and snapshot() sorts
        #    it, so a search cut short still hands back everything scored.
        record.results.extend(matched + reused)
        await store.save_matches(record.id, matched)

    async def _browse_with_retry(
        self,
        record: _SearchRecord,
        llm: LLM,
        company: CompanyInput,
        profile: CandidateProfile,
        browser,
        progress: CompanyProgress,
    ):
        async def on_progress(examined: int, found: int) -> None:
            progress.jobs_examined = examined
            progress.jobs_found = found

        async def on_status(message: str) -> None:
            progress.status = "running"
            progress.message = message

        last_error: Exception | None = None
        for attempt in range(1, DISCOVERY_ATTEMPTS + 1):
            try:
                progress.status = "running"
                progress.message = (
                    "Browsing careers site..."
                    if attempt == 1
                    else f"Retrying after error (attempt {attempt}/{DISCOVERY_ATTEMPTS})..."
                )
                jobs = await discover_company_jobs(
                    llm,
                    company,
                    profile,
                    browser,
                    freshness=record.freshness,
                    locations=record.locations,
                    context_gate=self._context_gate,
                    on_progress=on_progress,
                    on_status=on_status,
                )
                progress.jobs_examined = max(progress.jobs_examined, len(jobs))
                progress.jobs_found = len(jobs)
                progress.status = "completed"
                # A run that ends with nothing is not a success worth showing
                # a tick against in silence - say why. The agent's own last
                # status ("Out of time...", "the model did not answer...")
                # explains it; only clear the message when there is something
                # to show for the run.
                if jobs:
                    progress.message = None
                elif not progress.message or progress.message.startswith("Browsing"):
                    progress.message = "Nothing found on this site."
                return jobs
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - isolated per company
                last_error = exc
                # Retry is for transient trouble - a flaky page load, a site
                # that briefly refused us. Re-running a whole company because
                # the MODEL was slow just asks the same busy server the same
                # questions for another full budget, which is how a 6-minute
                # failure became a 13-minute one.
                retryable = _is_retryable(exc)
                logger.warning(
                    "discovery attempt %d/%d failed (%s): %s",
                    attempt,
                    DISCOVERY_ATTEMPTS,
                    "will retry" if retryable and attempt < DISCOVERY_ATTEMPTS else "giving up",
                    exc,
                    extra={"event": "discovery.failed", "retryable": retryable},
                )
                if not retryable:
                    break
                if attempt < DISCOVERY_ATTEMPTS:
                    await asyncio.sleep(DISCOVERY_RETRY_BACKOFF_S)

        assert last_error is not None
        raise last_error


# Shared manager instance for the app process.
search_manager = SearchManager()
