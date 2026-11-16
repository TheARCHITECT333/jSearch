"""Pydantic models shared across the backend.

All LLM structured output is validated through these models.
Malformed data must never be silently accepted.
"""

from __future__ import annotations

from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------


class LLMConfig(BaseModel):
    """LLM connection settings sent by the frontend per request.

    API keys live only in transit; the backend never persists or logs them.
    """

    provider: Literal["ollama", "openai-compatible"]
    base_url: str = ""
    model: str = ""
    api_key: Optional[str] = None

    @field_validator("base_url", "model", mode="before")
    @classmethod
    def _blank_to_default(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None if v is None else ""
        return v


# ---------------------------------------------------------------------------
# Candidate profile (extracted from the LaTeX resume)
# ---------------------------------------------------------------------------


class Skills(BaseModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    cloud: list[str] = Field(default_factory=list)
    infrastructure: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)


class ExperienceItem(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[str] = None
    highlights: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    year: Optional[str] = None


class CandidateProfile(BaseModel):
    name: Optional[str] = None
    summary: Optional[str] = None
    target_roles: list[str] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    years_experience: Optional[int] = Field(default=None, ge=0, le=60)
    preferred_locations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


class CompanyInput(BaseModel):
    name: str = Field(min_length=1)
    careers_url: str

    @field_validator("careers_url")
    @classmethod
    def _must_be_http_url(cls, v: str) -> str:
        parsed = urlparse(v.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"careers_url must be a valid HTTP/HTTPS URL, got: {v!r}")
        return v.strip()


# ---------------------------------------------------------------------------
# Discovered jobs / matches / final results
# ---------------------------------------------------------------------------


class DiscoveredJob(BaseModel):
    """A job found by a browser agent. The URL is mandatory and real."""

    title: str
    url: str
    location: Optional[str] = None
    employment_type: Optional[str] = None
    # Posting date EXACTLY as shown on the page (ISO date preferred, or a
    # relative phrase like "2 weeks ago"). Never guessed by the LLM.
    posted_at: Optional[str] = None
    description: str = ""
    requirements: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)
    source_url: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("job title must not be blank")
        return cleaned

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, v: str) -> str:
        parsed = urlparse(v.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"job url must be a valid HTTP/HTTPS URL, got: {v!r}")
        return v.strip()


SeniorityBand = Literal["intern", "junior", "mid", "senior", "staff", "principal"]


class MatchResult(BaseModel):
    """How good a fit this job is, and whether the application could survive.

    Those are two different questions. `overall_score` and the four *_fit
    axes answer "would I do well here". `disqualifiers` answers "is there a
    stated, non-negotiable bar I fail" - and it is a GATE, not a penalty: a
    job with any disqualifier leaves the ranking entirely instead of losing
    a few points and still sitting fourth in the list.
    """

    overall_score: int = Field(ge=0, le=100)
    role_fit: int = Field(ge=0, le=100)
    skill_fit: int = Field(ge=0, le=100)
    experience_fit: int = Field(ge=0, le=100)
    location_fit: int = Field(ge=0, le=100)
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reason: str = ""

    # Hard bars stated by the posting that the profile fails, in the
    # posting's own words. Empty = nothing stated rules this application out.
    disqualifiers: list[str] = Field(default_factory=list)
    seniority_band: Optional[SeniorityBand] = None
    required_years: Optional[int] = Field(default=None, ge=0, le=40)

    # Computed in Python after the LLM answers, never asked of the model.
    # 0 means "the posting listed no requirements to check", not "no match".
    keyword_coverage: int = Field(default=0, ge=0, le=100)
    missing_keywords: list[str] = Field(default_factory=list)

    @property
    def disqualified(self) -> bool:
        return bool(self.disqualifiers)


class JobResult(BaseModel):
    """Final result shape returned to the frontend."""

    company: str
    company_url: Optional[str] = None
    careers_url: Optional[str] = None

    job_title: str
    job_url: str
    location: Optional[str] = None
    employment_type: Optional[str] = None

    description: str = ""
    requirements: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)

    match: MatchResult


# ---------------------------------------------------------------------------
# Search progress / status
# ---------------------------------------------------------------------------

CompanyStatusKind = Literal["pending", "running", "completed", "failed"]


class CompanyProgress(BaseModel):
    company: str
    status: CompanyStatusKind = "pending"
    jobs_examined: int = 0
    jobs_found: int = 0
    message: Optional[str] = None


SearchStatusKind = Literal["queued", "running", "completed", "failed", "cancelled"]


class SearchStatus(BaseModel):
    id: str
    status: SearchStatusKind
    companies: list[CompanyProgress] = Field(default_factory=list)
    results: list[JobResult] = Field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# API request/response bodies
# ---------------------------------------------------------------------------


class ProfileRequest(BaseModel):
    resume_latex: str = Field(min_length=1)
    llm: Optional[LLMConfig] = None


class ScoreRequest(ProfileRequest):
    # 0-1 years -> junior, 2-5 -> mid, more than 5 -> senior.
    level: Literal["junior", "mid", "senior"] = "junior"


class ProfileResponse(BaseModel):
    profile: CandidateProfile


class SearchRequestCompany(BaseModel):
    name: str = Field(min_length=1)
    careers_url: str


FreshnessLevel = Literal["any", "24h", "3d", "1w", "2w", "1m"]


class SearchRequest(BaseModel):
    resume_latex: str = Field(min_length=1)
    companies: list[SearchRequestCompany] = Field(min_length=1)
    freshness: FreshnessLevel = "any"
    # Target locations for this search. Empty = no location restriction.
    locations: list[str] = Field(default_factory=list)
    llm: Optional[LLMConfig] = None


class StartSearchResponse(BaseModel):
    search_id: str
