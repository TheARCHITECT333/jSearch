"""Matcher tests: valid output, retry on malformed, clear failure."""

from __future__ import annotations

import json

import pytest

from app.llm import LLMInvalidOutputError
from app.matching.matcher import MatchingError, match_job
from app.schemas import DiscoveredJob
from tests.conftest import VALID_MATCH_JSON, FakeLLM, valid_profile

JOB = DiscoveredJob(
    title="Senior Backend Engineer",
    url="https://stripe.com/jobs/listing/123",
    location="Bangalore",
    employment_type="Full-time",
    description="Build payments APIs with Go and PostgreSQL.",
    requirements=["Go", "AWS", "PostgreSQL"],
)


class TestMatchJob:
    async def test_valid_match(self):
        llm = FakeLLM([VALID_MATCH_JSON])
        match = await match_job(llm, valid_profile(), JOB)
        assert match.overall_score == 94
        assert "Go" in match.matching_skills
        assert match.missing_skills == ["Kubernetes"]

    async def test_malformed_then_retry(self):
        llm = FakeLLM(["oops", VALID_MATCH_JSON])
        match = await match_job(llm, valid_profile(), JOB)
        assert match.skill_fit == 95
        assert len(llm.calls) == 2
        # The retry prompt must contain feedback about the invalid attempt.
        assert "previous response was invalid" in llm.calls[1][1]

    async def test_invalid_twice_raises_matching_error_path(self):
        bad = json.dumps({"overall_score": "excellent"})
        llm = FakeLLM([bad, bad])
        with pytest.raises(LLMInvalidOutputError):
            await match_job(llm, valid_profile(), JOB)

    async def test_prompt_contains_profile_and_job_only(self):
        llm = FakeLLM([VALID_MATCH_JSON])
        await match_job(llm, valid_profile(), JOB)
        system, user = llm.calls[0]
        combined = system + user
        # Profile context is present...
        assert "Backend Engineer" in combined or "target_roles" in combined
        # ...and the job description is present.
        assert "payments APIs" in combined

    async def test_requested_locations_included_in_prompt(self):
        llm = FakeLLM([VALID_MATCH_JSON])
        await match_job(llm, valid_profile(), JOB, locations=["Bangalore", "Remote"])
        _, user = llm.calls[0]
        assert "requested_locations: Bangalore, Remote" in user
        assert "REQUESTED locations" in user

    async def test_no_locations_omits_search_context(self):
        llm = FakeLLM([VALID_MATCH_JSON])
        await match_job(llm, valid_profile(), JOB)
        _, user = llm.calls[0]
        assert "requested_locations" not in user
