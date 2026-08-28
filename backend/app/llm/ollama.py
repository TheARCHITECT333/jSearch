"""Ollama provider (Ollama HTTP API - local or any hosted Ollama server).

Works with plain `http://localhost:11434`, Docker's
`http://host.docker.internal:11434`, and hosted Ollama endpoints such as
`https://example.com/ollama`. Hosts that require authentication accept an
optional API key sent as a Bearer token.
"""

from __future__ import annotations

import httpx

from .base import LLMAvailabilityError, LLM, LLMError, timed_llm_call

DEFAULT_TIMEOUT_SECONDS = 180.0


class OllamaLLM(LLM):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        # Applied per-request (not at client level) so an injected client
        # still receives credentials.
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.AsyncClient(timeout=timeout)

    @property
    def model_name(self) -> str:
        return self.model

    async def generate(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
        }
        async with timed_llm_call(self.model):
            try:
                response = await self._client.post(
                    f"{self.base_url}/api/chat", json=payload, headers=self._headers
                )
            except httpx.TimeoutException as exc:
                raise LLMError(
                    f"Ollama timed out after {DEFAULT_TIMEOUT_SECONDS:.0f}s while calling "
                    f"model '{self.model}'. Try a smaller/faster model."
                ) from exc
            except httpx.HTTPError as exc:
                raise LLMAvailabilityError(
                    f"Could not connect to Ollama at {self.base_url}. "
                    "Check the base URL and your network."
                ) from exc

        if response.status_code == 404:
            raise LLMError(
                f"Model '{self.model}' was not found on the Ollama server at "
                f"{self.base_url} (HTTP 404). Check the model name - on a hosted "
                "server ask its owners which models are available."
            )
        if response.status_code in (401, 403):
            raise LLMError(
                "The Ollama server rejected the credentials (HTTP 401/403). "
                "This host requires an API key - enter it in the LLM settings."
            )
        if response.status_code != 200:
            raise LLMError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        content = (
            data.get("message", {}).get("content")
            if isinstance(data.get("message"), dict)
            else None
        )
        if not content and isinstance(data.get("response"), str):
            # /api/generate-style responses for compatibility.
            content = data["response"]
        if not isinstance(content, str):
            raise LLMError("Ollama returned an unexpected response shape.")
        return content

    async def close(self) -> None:
        await self._client.aclose()
