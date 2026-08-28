"""Discovery orchestration for one company: browser agent + dedup."""

from __future__ import annotations

import logging

from ..agents.career_agent import CareerAgent, CareerAgentError
from ..llm import LLM
from ..schemas import CandidateProfile, CompanyInput, DiscoveredJob
from .dedup import deduplicate_jobs

logger = logging.getLogger(__name__)


async def discover_company_jobs(
    llm: LLM,
    company: CompanyInput,
    profile: CandidateProfile,
    browser,
    *,
    freshness: str = "any",
    locations: list[str] | None = None,
    context_gate=None,
    on_progress=None,
    on_status=None,
) -> list[DiscoveredJob]:
    """Run one read-only browser agent against a careers site.

    Raises CareerAgentError (or any other exception) on failure; the caller
    decides whether to continue with remaining companies.
    """
    agent = CareerAgent(
        llm=llm,
        company_name=company.name,
        careers_url=company.careers_url,
        profile=profile,
        freshness=freshness,
        locations=locations,
    )
    agent.set_callbacks(on_progress=on_progress, on_status=on_status)
    try:
        jobs = await agent.run(browser, context_gate=context_gate)
    except Exception as exc:  # noqa: BLE001
        logger.exception("career agent failed")
        raise CareerAgentError(str(exc) or exc.__class__.__name__) from exc

    unique = deduplicate_jobs(jobs)
    logger.info("discovered %d unique jobs", len(unique))
    return unique
