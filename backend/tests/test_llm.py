"""LLM abstraction tests: JSON extraction, retry, provider errors.

Uses httpx.MockTransport so no real Ollama/OpenAI server is needed.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.llm import (
    LLMAvailabilityError,
    LLMError,
    LLMInvalidOutputError,
    OllamaLLM,
    OpenAICompatibleLLM,
    extract_json,
    generate_validated,
)
from app.schemas import CandidateProfile, MatchResult
from tests.conftest import VALID_PROFILE_JSON, FakeLLM


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        text = "Here you go:\n```json\n{\"a\": [1, 2]}\n```\nDone."
        assert extract_json(text) == {"a": [1, 2]}

    def test_prose_then_object(self):
        text = 'Sure! The profile is {"a": 1} as requested.'
        assert extract_json(text) == {"a": 1}

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            extract_json("no json here at all")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            extract_json("")


# ---------------------------------------------------------------------------
# generate_validated: profile + match validation & retry behavior
# ---------------------------------------------------------------------------


class TestGenerateValidated:
    async def test_valid_profile_output(self):
        llm = FakeLLM([VALID_PROFILE_JSON])
        profile = await generate_validated(llm, "s", "u", CandidateProfile)
        assert profile.name == "Shubh Sharma"

    async def test_malformed_then_retry_succeeds(self):
        llm = FakeLLM(["I cannot do that.", VALID_PROFILE_JSON])
        profile = await generate_validated(llm, "s", "u", CandidateProfile)
        assert profile.target_roles == ["Backend Engineer", "Software Engineer"]
        assert len(llm.calls) == 2

    async def test_invalid_twice_raises_clear_error(self):
        llm = FakeLLM(["garbage", '{"name": 12345, "skills": "nope"}'])
        with pytest.raises(LLMInvalidOutputError) as excinfo:
            await generate_validated(llm, "s", "u", CandidateProfile)
        assert "invalid structured data" in str(excinfo.value)

    async def test_valid_match_output(self):
        payload = {
            "overall_score": 80,
            "role_fit": 85,
            "skill_fit": 75,
            "experience_fit": 80,
            "location_fit": 90,
            "matching_skills": ["Go"],
            "missing_skills": [],
            "reason": "ok",
        }
        llm = FakeLLM([json.dumps(payload)])
        match = await generate_validated(llm, "s", "u", MatchResult)
        assert match.overall_score == 80

    async def test_match_out_of_bounds_rejected_after_retry(self):
        bad = json.dumps(
            {
                "overall_score": 150,
                "role_fit": 50,
                "skill_fit": 50,
                "experience_fit": 50,
                "location_fit": 50,
            }
        )
        llm = FakeLLM([bad, bad])
        with pytest.raises(LLMInvalidOutputError):
            await generate_validated(llm, "s", "u", MatchResult)


# ---------------------------------------------------------------------------
# Provider HTTP behaviour via MockTransport
# ---------------------------------------------------------------------------


def ollama_with(handler) -> OllamaLLM:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return OllamaLLM(base_url="http://ollama.test", model="qwen3:30b", client=client)


def openai_with(handler) -> OpenAICompatibleLLM:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return OpenAICompatibleLLM(
        base_url="http://api.test/v1", model="m", api_key="sk-test", client=client
    )


class TestOllamaProvider:
    async def test_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["model"] == "qwen3:30b"
            assert body["messages"][0]["role"] == "system"
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "hi"}})

        llm = ollama_with(handler)
        assert await llm.generate("s", "u") == "hi"
        await llm.close()

    async def test_optional_api_key_sent_as_bearer_token(self):
        seen_headers = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_headers["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "hi"}})

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        llm = OllamaLLM(
            base_url="https://hosted.example/ollama",
            model="qwen3:32b",
            api_key="secret-token",
            client=client,
        )
        assert await llm.generate("s", "u") == "hi"
        assert seen_headers["auth"] == "Bearer secret-token"

        # Without a key no Authorization header is sent.
        seen_headers.clear()
        plain_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        plain = OllamaLLM(
            base_url="http://localhost:11434", model="m", client=plain_client
        )
        await plain.generate("s", "u")
        assert seen_headers.get("auth") is None
        await llm.close()
        await plain.close()

    async def test_auth_rejection_is_friendly(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        llm = ollama_with(handler)
        with pytest.raises(LLMError) as excinfo:
            await llm.generate("s", "u")
        assert "API key" in str(excinfo.value)
        await llm.close()

    async def test_connection_failure_is_friendly(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        llm = ollama_with(handler)
        with pytest.raises(LLMAvailabilityError) as excinfo:
            await llm.generate("s", "u")
        assert "Could not connect to Ollama" in str(excinfo.value)
        await llm.close()

    async def test_timeout_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow")

        llm = ollama_with(handler)
        with pytest.raises(LLMError) as excinfo:
            await llm.generate("s", "u")
        assert "timed out" in str(excinfo.value)
        await llm.close()

    async def test_missing_model_404(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "model not found"})

        llm = ollama_with(handler)
        with pytest.raises(LLMError) as excinfo:
            await llm.generate("s", "u")
        assert "was not found on the Ollama server" in str(excinfo.value)
        await llm.close()


class TestOpenAICompatibleProvider:
    async def test_success_and_auth_header(self):
        seen_headers = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_headers["auth"] = request.headers.get("Authorization")
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "hello"}}]},
            )

        llm = openai_with(handler)
        assert await llm.generate("s", "u") == "hello"
        assert seen_headers["auth"] == "Bearer sk-test"
        await llm.close()

    async def test_bad_key_401(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        llm = openai_with(handler)
        with pytest.raises(LLMError) as excinfo:
            await llm.generate("s", "u")
        assert "API key" in str(excinfo.value)
        await llm.close()

    async def test_connection_failure(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("dns fail")

        llm = openai_with(handler)
        with pytest.raises(LLMAvailabilityError):
            await llm.generate("s", "u")
        await llm.close()
