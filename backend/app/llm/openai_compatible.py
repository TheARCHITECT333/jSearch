"""OpenAI-compatible provider (chat/completions interface).

Works with OpenAI itself and with common compatible servers
(vLLM, LM Studio, LiteLLM, OpenRouter, ...).
"""

from __future__ import annotations

import httpx

from .base import LLMAvailabilityError, LLM, LLMError, timed_llm_call

DEFAULT_TIMEOUT_SECONDS = 180.0


class OpenAICompatibleLLM(LLM):
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
            "temperature": 0.1,
        }
        async with timed_llm_call(self.model):
            try:
                response = await self._client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=self._headers
                )
            except httpx.TimeoutException as exc:
                raise LLMError(
                    f"The LLM API timed out after {DEFAULT_TIMEOUT_SECONDS:.0f}s while "
                    f"calling model '{self.model}'."
                ) from exc
            except httpx.HTTPError as exc:
                raise LLMAvailabilityError(
                    f"Could not connect to the LLM API at {self.base_url}. "
                    "Check the base URL and your network."
                ) from exc

        if response.status_code in (401, 403):
            raise LLMError("The LLM API rejected the credentials (HTTP 401/403). Check the API key.")
        if response.status_code == 404:
            raise LLMError(
                f"Model '{self.model}' was not found at {self.base_url} (HTTP 404). "
                "Check the base URL (it should usually end in /v1) and the model name."
            )
        if response.status_code != 200:
            raise LLMError(
                f"The LLM API returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise LLMError("The LLM API returned an unexpected response shape.") from exc

        if not isinstance(content, str):
            raise LLMError("The LLM API returned an empty completion.")
        return content

    async def close(self) -> None:
        await self._client.aclose()
