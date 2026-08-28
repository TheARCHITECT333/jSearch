"""Job matching against the candidate profile.

Matching is fully separate from browser discovery: it only sees a
validated profile and a validated discovered job.
"""

from __future__ import annotations

import json
import logging

from ..llm import LLM, LLMError, generate_validated
from ..schemas import CandidateProfile, DiscoveredJob, MatchResult
from .keywords import coverage

logger = logging.getLogger(__name__)

MATCH_SYSTEM_PROMPT = """\
You are a strict technical recruiter. You receive a candidate profile and one \
job posting, and must answer TWO separate questions as one JSON object:

1. FIT - would this candidate do well in this job? (the *_fit scores)
2. ELIGIBILITY - does the posting state a hard bar this candidate fails?
   (disqualifiers)

Never mix them. A candidate can be a superb fit for a job they are not \
allowed to apply for, and a poor fit for one they are perfectly eligible for.

Rules:
- Output ONLY one JSON object. No prose, no markdown fences.
- All scores are integers 0-100.
- overall_score should weigh role_fit, skill_fit, experience_fit and location_fit.
- matching_skills: candidate skills the job asks for (use the candidate's wording).
- missing_skills: important requirements the candidate lacks (max 5).
- reason: 1-3 short sentences explaining the score.
- Be honest: do not inflate scores for weak matches.
- If the location is unacceptable for the candidate and not remote, cap location_fit low.
- seniority_band: the level the POSTING is written for, one of
  intern, junior, mid, senior, staff, principal. null if genuinely unclear.
- required_years: the minimum years of experience the posting demands as a
  number, or null if it does not state one.

disqualifiers is a list of SHORT phrases quoting the posting's own wording.
Add an entry ONLY when the posting states a hard, non-negotiable bar and the
profile clearly fails it or cannot satisfy it. Legitimate reasons:
- a years-of-experience minimum well above the candidate's (2+ years above),
- a seniority level far from the candidate's (e.g. staff/principal for a
  junior candidate, or an internship for a senior one),
- work authorization, citizenship or security clearance the posting requires
  and the profile gives no evidence of,
- a mandatory on-site location the candidate cannot work from,
- a mandatory credential the candidate lacks (specific degree, licence).

NEVER add a disqualifier for:
- missing technical skills (that is missing_skills),
- anything the posting calls preferred, desired, nice-to-have or a plus,
- your own guesses about the candidate beyond what the profile says.

If nothing rules the candidate out, disqualifiers MUST be [].

JSON schema:
{
  "overall_score": integer,
  "role_fit": integer,
  "skill_fit": integer,
  "experience_fit": integer,
  "location_fit": integer,
  "matching_skills": string[],
  "missing_skills": string[],
  "reason": string,
  "disqualifiers": string[],
  "seniority_band": string | null,
  "required_years": integer | null
}
"""


class MatchingError(LLMError):
    pass


def _profile_brief(profile: CandidateProfile) -> str:
    skills = profile.skills
    lines = [
        f"Name: {profile.name or 'unknown'}",
        f"Target roles: {', '.join(profile.target_roles) or 'unknown'}",
        f"Years of experience: {profile.years_experience if profile.years_experience is not None else 'unknown'}",
        f"Preferred locations: {', '.join(profile.preferred_locations) or 'unspecified'}",
        "Skills:",
        f"  languages: {', '.join(skills.languages)}",
        f"  frameworks: {', '.join(skills.frameworks)}",
        f"  databases: {', '.join(skills.databases)}",
        f"  cloud: {', '.join(skills.cloud)}",
        f"  infrastructure: {', '.join(skills.infrastructure)}",
        f"  tools: {', '.join(skills.tools)}",
        f"  other: {', '.join(skills.other)}",
    ]
    if profile.summary:
        lines.append(f"Summary: {profile.summary[:500]}")
    return "\n".join(lines)


async def match_job(
    llm: LLM,
    profile: CandidateProfile,
    job: DiscoveredJob,
    *,
    locations: list[str] | None = None,
    resume_latex: str = "",
) -> MatchResult:
    """Score one job. `resume_latex` is the RAW resume, used only for the
    literal keyword coverage the LLM is deliberately not asked about."""
    requested = [loc.strip() for loc in (locations or []) if loc.strip()]
    user_prompt = (
        f"<candidate_profile>\n{_profile_brief(profile)}\n</candidate_profile>\n\n"
        f"<search_context>\n"
        + (
            f"requested_locations: {', '.join(requested)}\n"
            "Judge location_fit against these REQUESTED locations "
            "(remote/hybrid roles satisfy any location request).\n"
            if requested
            else ""
        )
        + "</search_context>\n\n"
        f"<job_posting url=\"{job.url}\">\n"
        f"title: {job.title}\n"
        f"location: {job.location or 'unspecified'}\n"
        f"employment_type: {job.employment_type or 'unspecified'}\n"
        f"posted_date: {job.posted_at or 'unknown'}\n"
        f"requirements: {json.dumps(job.requirements)}\n"
        f"description:\n{job.description[:6000]}\n"
        "</job_posting>\n\n"
        "Return the match evaluation JSON now."
    )
    try:
        result = await generate_validated(
            llm, MATCH_SYSTEM_PROMPT, user_prompt, MatchResult
        )
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected matching failure")
        raise MatchingError(f"Failed to evaluate match for job '{job.title}'.") from exc

    # The model is not asked for these - it would answer semantically, which
    # is the exact blind spot they exist to cover.
    if resume_latex:
        result.keyword_coverage, missing = coverage(
            resume_latex, job.requirements, job.title
        )
        result.missing_keywords = missing[:10]

    if result.disqualifiers:
        logger.info(
            "ruled out %r: %s",
            job.title,
            "; ".join(result.disqualifiers),
            extra={
                "event": "match.disqualified",
                "disqualifiers": list(result.disqualifiers),
            },
        )
    return result
