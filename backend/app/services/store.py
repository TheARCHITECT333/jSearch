"""Persistence operations for the search pipeline.

Everything here is best-effort from the search's perspective: a DB failure
logs a warning and degrades to "no history" instead of failing the search.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models import Job as JobRow
from ..models import Match as MatchRow
from ..models import Profile as ProfileRow
from ..models import Search as SearchRow
from ..schemas import (
    CandidateProfile,
    DiscoveredJob,
    JobResult,
    LLMConfig,
    SearchStatus,
)
from .dedup import normalize_job_url

logger = logging.getLogger(__name__)


def resume_hash(latex: str) -> str:
    return hashlib.sha256(latex.encode("utf-8")).hexdigest()


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_job_url(url).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


async def find_cached_profile(resume_latex: str) -> CandidateProfile | None:
    """Return the cached profile for this exact resume, if we parsed it before."""
    from ..db import session_factory

    try:
        async with session_factory()() as session:
            row = (
                await session.execute(
                    select(ProfileRow).where(
                        ProfileRow.resume_hash == resume_hash(resume_latex)
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return CandidateProfile.model_validate(row.profile_json)
    except Exception:  # noqa: BLE001 - cache miss on any DB trouble
        logger.warning("profile cache lookup failed", exc_info=True)
        return None


async def save_profile(
    resume_latex: str, profile: CandidateProfile, model_used: str | None = None
) -> None:
    from ..db import session_factory

    try:
        h = resume_hash(resume_latex)
        async with session_factory()() as session:
            row = (
                await session.execute(
                    select(ProfileRow).where(ProfileRow.resume_hash == h)
                )
            ).scalar_one_or_none()
            if row is not None:
                row.profile_json = profile.model_dump()
                row.model_used = model_used
            else:
                session.add(
                    ProfileRow(
                        resume_hash=h,
                        profile_json=profile.model_dump(),
                        model_used=model_used,
                    )
                )
            await session.commit()
    except IntegrityError:
        # Two searches on the same resume started together and both missed
        # the cache. The other one won; the row we wanted now exists, so
        # there is nothing to warn about.
        logger.debug(
            "profile already cached by a concurrent search",
            extra={"event": "profile.cache_race"},
        )
    except Exception:  # noqa: BLE001
        logger.warning("failed to persist profile", exc_info=True)


async def extract_profile_cached(llm, resume_latex: str, llm_config: LLMConfig) -> tuple[CandidateProfile, bool]:
    """Extract via LLM unless we already parsed this exact resume.
    Returns (profile, was_cached)."""
    from .resume import extract_profile

    cached = await find_cached_profile(resume_latex)
    if cached is not None:
        logger.info("profile cache hit - skipping LLM extraction")
        return cached, True
    profile = await extract_profile(llm, resume_latex)
    await save_profile(resume_latex, profile, model_used=_model_name(llm_config))
    return profile, False


def _model_name(llm_config) -> str | None:
    model = getattr(llm_config, "model", None)
    if model is None and isinstance(llm_config, dict):
        model = llm_config.get("model")
    return str(model) if model else None


# ---------------------------------------------------------------------------
# Jobs & matches
# ---------------------------------------------------------------------------

async def upsert_jobs(
    jobs: Sequence[DiscoveredJob],
    attribution: dict[str, tuple[str | None, str | None]] | None = None,
) -> dict[str, int]:
    """Insert-or-touch job rows; returns mapping url_hash -> job id.

    `attribution` optionally maps url_hash -> (company name, careers URL) so
    history rows know which company a posting came from.
    """
    from ..db import session_factory

    mapping: dict[str, int] = {}
    if not jobs:
        return mapping
    try:
        async with session_factory()() as session:
            for job in jobs:
                h = url_hash(job.url)
                row = (
                    await session.execute(
                        select(JobRow).where(JobRow.url_hash == h)
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = JobRow(url_hash=h, url=job.url)
                    session.add(row)
                company, careers_url = (attribution or {}).get(h, (None, None))
                if company:
                    row.company = company
                if careers_url:
                    row.careers_url = careers_url
                row.title = job.title
                row.location = job.location
                row.employment_type = job.employment_type
                row.posted_at_text = job.posted_at
                row.description = job.description[:8000]
                row.requirements_json = list(job.requirements)
                row.preferred_qualifications_json = list(job.preferred_qualifications)
                row.last_seen_at = datetime.now(timezone.utc)
                await session.flush()
                mapping[h] = row.id
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("failed to upsert jobs", exc_info=True)
    return mapping


async def find_recently_matched(
    jobs: Sequence[DiscoveredJob], ttl_days: float
) -> dict[str, MatchRow]:
    """For each job matched within `ttl_days`, return its most recent match
    row keyed by url_hash."""
    from ..db import session_factory

    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    hashes = [url_hash(j.url) for j in jobs]
    if not hashes:
        return {}

    result: dict[str, MatchRow] = {}
    try:
        async with session_factory()() as session:
            rows = (
                await session.execute(
                    select(MatchRow, JobRow)
                    .join(JobRow, MatchRow.job_id == JobRow.id)
                    .where(JobRow.url_hash.in_(hashes), MatchRow.created_at >= cutoff)
                    .order_by(MatchRow.created_at.desc())
                )
            ).all()
            for match_row, job_row in rows:
                result.setdefault(job_row.url_hash, match_row)
    except Exception:  # noqa: BLE001
        logger.warning("failed to look up recently-matched jobs", exc_info=True)
    return result


async def save_matches(search_id: str, results: Iterable[JobResult]) -> None:
    """Persist matches for a finished search (jobs are upserted as needed)."""
    from ..db import session_factory

    results = list(results)
    if not results:
        return
    try:
        job_ids = await upsert_jobs(
            [_result_to_discovered(r) for r in results],
            attribution={
                url_hash(r.job_url): (r.company, r.careers_url) for r in results
            },
        )
        async with session_factory()() as session:
            for result in results:
                job_id = job_ids.get(url_hash(result.job_url))
                if job_id is None:
                    continue
                existing_id = (
                    await session.execute(
                        select(MatchRow.id).where(
                            MatchRow.search_id == search_id,
                            MatchRow.job_id == job_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing_id is not None:
                    continue  # keep the original evaluation for this search
                session.add(
                    MatchRow(
                        search_id=search_id,
                        job_id=job_id,
                        overall_score=result.match.overall_score,
                        role_fit=result.match.role_fit,
                        skill_fit=result.match.skill_fit,
                        experience_fit=result.match.experience_fit,
                        location_fit=result.match.location_fit,
                        matching_skills_json=list(result.match.matching_skills),
                        missing_skills_json=list(result.match.missing_skills),
                        reason=result.match.reason,
                        disqualifiers_json=list(result.match.disqualifiers),
                        seniority_band=result.match.seniority_band,
                        required_years=result.match.required_years,
                        keyword_coverage=result.match.keyword_coverage,
                        missing_keywords_json=list(result.match.missing_keywords),
                    )
                )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("failed to persist matches", exc_info=True)


def _result_to_discovered(result: JobResult) -> DiscoveredJob:
    return DiscoveredJob(
        title=result.job_title,
        url=result.job_url,
        location=result.location,
        employment_type=result.employment_type,
        description=result.description,
        requirements=list(result.requirements),
        preferred_qualifications=list(result.preferred_qualifications),
    )


# ---------------------------------------------------------------------------
# Search history
# ---------------------------------------------------------------------------


async def record_search_started(
    search_id: str,
    companies: list[tuple[str, str]],
    freshness: str,
    locations: list[str],
) -> None:
    from ..db import session_factory

    try:
        async with session_factory()() as session:
            session.add(
                SearchRow(
                    id=search_id,
                    status="queued",
                    freshness=freshness,
                    locations_json=list(locations),
                    companies_json=[
                        {"name": n, "careers_url": u} for n, u in companies
                    ],
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("failed to record search start", exc_info=True)


async def record_search_finished(status: SearchStatus) -> None:
    from ..db import session_factory

    try:
        async with session_factory()() as session:
            row = await session.get(SearchRow, status.id)
            if row is None:
                return
            row.status = status.status
            row.error = status.error
            row.completed_at = datetime.now(timezone.utc)
            row.final_snapshot_json = status.model_dump(mode="json")
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("failed to record search finish", exc_info=True)


async def load_search_history(search_id: str) -> SearchStatus | None:
    """Rebuild a terminal search's status after a backend restart."""
    from ..db import session_factory

    try:
        async with session_factory()() as session:
            row = await session.get(SearchRow, search_id)
            if row is None:
                return None
            if row.final_snapshot_json:
                return SearchStatus.model_validate(row.final_snapshot_json)
            return SearchStatus(
                id=row.id,
                status=row.status,  # type: ignore[arg-type]
                error=row.error,
            )
    except Exception:  # noqa: BLE001
        logger.warning("failed to load search history", exc_info=True)
        return None


async def list_recent_searches(limit: int = 20) -> list[dict]:
    from ..db import session_factory

    try:
        async with session_factory()() as session:
            rows = (
                await session.execute(
                    select(SearchRow)
                    .order_by(SearchRow.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [
                {
                    "id": r.id,
                    "status": r.status,
                    "freshness": r.freshness,
                    "locations": r.locations_json or [],
                    "created_at": r.created_at.isoformat(),
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "error": r.error,
                    "result_count": len((r.final_snapshot_json or {}).get("results", [])),
                }
                for r in rows
            ]
    except Exception:  # noqa: BLE001
        logger.warning("failed to list searches", exc_info=True)
        return []

