"""Candidate profile extraction from a LaTeX resume via the LLM."""

from __future__ import annotations

import logging

from ..llm import LLM, LLMError, generate_validated
from ..schemas import CandidateProfile

logger = logging.getLogger(__name__)

PROFILE_SYSTEM_PROMPT = """\
You are a precise resume-parsing assistant. You receive the LaTeX source of a \
resume and must extract a structured candidate profile as JSON.

Rules:
- Output ONLY one JSON object. No prose, no markdown fences.
- Use null for unknown optional values and [] for unknown lists.
- Never invent skills, roles, companies or numbers that are not in the resume.
- Group skills into: languages, frameworks, databases, cloud, infrastructure, tools, other.
- years_experience is an integer estimate based on work history (null if unclear).
- target_roles should reflect the jobs this person is looking for.
- preferred_locations should list cities/regions/remote preferences found in the resume.

JSON schema:
{
  "name": string | null,
  "summary": string | null,
  "target_roles": string[],
  "skills": {
    "languages": string[], "frameworks": string[], "databases": string[],
    "cloud": string[], "infrastructure": string[], "tools": string[], "other": string[]
  },
  "experience": [{"company": string|null, "title": string|null, "duration": string|null, "highlights": string[]}],
  "education": [{"institution": string|null, "degree": string|null, "year": string|null}],
  "years_experience": integer | null,
  "preferred_locations": string[]
}
"""


class ResumeExtractionError(LLMError):
    pass


async def extract_profile(llm: LLM, resume_latex: str) -> CandidateProfile:
    latex = resume_latex.strip()
    if len(latex) < 40:
        raise ResumeExtractionError(
            "The resume content looks too short to parse. Upload a complete .tex file."
        )

    try:
        return await generate_validated(
            llm,
            PROFILE_SYSTEM_PROMPT,
            f"<resume_latex>\n{latex[:24000]}\n</resume_latex>\n\nExtract the candidate profile JSON now.",
            CandidateProfile,
        )
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected profile extraction failure")
        raise ResumeExtractionError("Failed to extract the candidate profile from the resume.") from exc
