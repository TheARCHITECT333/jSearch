"""Schema validation tests: profile, companies, jobs, matches, URLs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    CandidateProfile,
    CompanyInput,
    DiscoveredJob,
    LLMConfig,
    MatchResult,
)


class TestCandidateProfile:
    def test_full_profile_validates(self):
        profile = CandidateProfile.model_validate(
            {
                "name": "A",
                "summary": None,
                "target_roles": ["Backend Engineer"],
                "skills": {"languages": ["Go"]},
                "experience": [{"company": "Acme", "title": "SWE"}],
                "education": [],
                "years_experience": 6,
                "preferred_locations": ["Remote"],
            }
        )
        assert profile.skills.languages == ["Go"]
        assert profile.years_experience == 6

    def test_defaults_are_empty_not_none(self):
        profile = CandidateProfile()
        assert profile.target_roles == []
        assert profile.skills.other == []
        assert profile.name is None

    def test_years_experience_bounds(self):
        with pytest.raises(ValidationError):
            CandidateProfile(years_experience=99)
        with pytest.raises(ValidationError):
            CandidateProfile(years_experience=-1)

    def test_rejects_wrong_types(self):
        with pytest.raises(ValidationError):
            CandidateProfile(target_roles="not-a-list")


class TestLLMConfig:
    def test_providers(self):
        assert LLMConfig(provider="ollama").provider == "ollama"
        assert LLMConfig(provider="openai-compatible").api_key is None

    def test_invalid_provider_rejected(self):
        with pytest.raises(ValidationError):
            LLMConfig(provider="anthropic")


class TestCompanyInput:
    @pytest.mark.parametrize(
        "url",
        [
            "https://stripe.com/jobs",
            "http://careers.google.com/jobs/results/",
            "https://boards.greenhouse.io/stripe",
        ],
    )
    def test_valid_urls_accepted(self, url):
        company = CompanyInput(name="Stripe", careers_url=url)
        assert company.careers_url == url

    @pytest.mark.parametrize("url", ["ftp://x.com/jobs", "not a url", "", "/relative/path"])
    def test_invalid_urls_rejected(self, url):
        with pytest.raises(ValidationError):
            CompanyInput(name="X", careers_url=url)

    def test_blank_name_rejected(self):
        with pytest.raises(ValidationError):
            CompanyInput(name="", careers_url="https://x.com/jobs")


class TestDiscoveredJob:
    def test_minimal_job(self):
        job = DiscoveredJob(title="Backend Engineer", url="https://x.com/jobs/1")
        assert job.requirements == []
        assert job.description == ""

    def test_url_is_mandatory_and_http(self):
        with pytest.raises(ValidationError):
            DiscoveredJob(title="T")
        with pytest.raises(ValidationError):
            DiscoveredJob(title="T", url="javascript:alert(1)")
        with pytest.raises(ValidationError):
            DiscoveredJob(title="T", url="gopher://old.example/x")

    def test_blank_title_rejected(self):
        with pytest.raises(ValidationError):
            DiscoveredJob(title="  ", url="https://x.com/j")


class TestMatchResult:
    def test_valid_match(self):
        match = MatchResult.model_validate(
            {
                "overall_score": 94,
                "role_fit": 96,
                "skill_fit": 95,
                "experience_fit": 90,
                "location_fit": 100,
                "matching_skills": ["Go"],
                "missing_skills": ["K8s"],
                "reason": "Great fit",
            }
        )
        assert match.overall_score == 94

    @pytest.mark.parametrize("field", ["overall_score", "role_fit", "skill_fit"])
    def test_scores_bounded_0_to_100(self, field):
        payload = {
            "overall_score": 50,
            "role_fit": 50,
            "skill_fit": 50,
            "experience_fit": 50,
            "location_fit": 50,
        }
        for bad in (-1, 101, "high"):
            payload[field] = bad
            with pytest.raises(ValidationError):
                MatchResult.model_validate(payload)
