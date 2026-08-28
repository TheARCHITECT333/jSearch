"""LLM package: provider implementations and the shared base class."""

from .base import (
    LLM,
    LLM_CONCURRENCY,
    LLMAvailabilityError,
    LLMError,
    LLMInvalidOutputError,
    extract_json,
    generate_validated,
    llm_gate,
    llm_slot,
    queued_seconds,
    timed_llm_call,
)
from .ollama import OllamaLLM
from .openai_compatible import OpenAICompatibleLLM

__all__ = [
    "LLM",
    "LLM_CONCURRENCY",
    "LLMAvailabilityError",
    "LLMError",
    "LLMInvalidOutputError",
    "OllamaLLM",
    "OpenAICompatibleLLM",
    "extract_json",
    "generate_validated",
    "llm_gate",
    "llm_slot",
    "queued_seconds",
    "timed_llm_call",
]
