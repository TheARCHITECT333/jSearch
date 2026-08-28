"""Resume profile extraction service tests."""

from __future__ import annotations

import pytest

from app.llm import LLMError
from app.services.resume import ResumeExtractionError, extract_profile
from tests.conftest import VALID_PROFILE_JSON, FakeLLM

LATEX = r"""\documentclass{article}
\begin{document}
\section{Experience}
Senior Engineer at Acme (2020-present). Built payment APIs in Go.
\end{document}
"""


class TestExtractProfile:
    async def test_valid_latex_produces_profile(self):
        llm = FakeLLM([VALID_PROFILE_JSON])
        profile = await extract_profile(llm, LATEX)
        assert profile.name == "Shubh Sharma"
        assert profile.skills.databases == ["PostgreSQL"]
        assert len(llm.calls) == 1

    async def test_too_short_resume_is_rejected_before_llm(self):
        llm = FakeLLM([])
        with pytest.raises(ResumeExtractionError):
            await extract_profile(llm, "hi")
        assert llm.calls == []  # never called the LLM

    async def test_malformed_output_retried_once(self):
        llm = FakeLLM(["not json", VALID_PROFILE_JSON])
        profile = await extract_profile(llm, LATEX)
        assert profile.years_experience == 6
        assert len(llm.calls) == 2

    async def test_persistent_invalid_output_raises_clear_error(self):
        llm = FakeLLM(["nope", "still nope"])
        with pytest.raises(LLMError) as excinfo:
            await extract_profile(llm, LATEX)
        assert "invalid structured data" in str(excinfo.value)

    async def test_availability_error_propagates(self):
        llm = FakeLLM([LLMError("Could not connect to Ollama.")])
        with pytest.raises(LLMError):
            await extract_profile(llm, LATEX)
