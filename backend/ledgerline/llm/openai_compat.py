"""Client for any OpenAI-compatible /chat/completions endpoint.

Works with OpenAI, Gemini's OpenAI-compatible endpoint, Groq, OpenRouter, vLLM and local
Ollama (OPENAI_BASE_URL=http://localhost:11434/v1, no key needed).
"""
from __future__ import annotations

import random
import time

import httpx

from .base import LLMResponse

# Retried: rate limits, timeouts, conflicts and server errors (the same set the Anthropic SDK retries).
# The provider rate-limited the starter on 18 of 63 document attempts; without a retry each one became a
# processing_error and an unnecessary review. Other 4xx errors mean the request itself is wrong: no retry.
RETRY_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})
BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
_sleep = time.sleep  # replaced in tests


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    """The provider's Retry-After if it sent one, else exponential backoff with jitter (1, 2, 4 s ...)."""
    retry_after = response.headers.get("retry-after") if response is not None else None
    if retry_after:
        try:
            return min(float(retry_after), MAX_BACKOFF_SECONDS)
        except ValueError:
            pass  # an HTTP date rather than seconds: fall back to backoff
    return min(BACKOFF_SECONDS * 2 ** attempt, MAX_BACKOFF_SECONDS) * random.uniform(0.5, 1.0)


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str | None, model: str, timeout: float = 120.0,
                 reasoning_effort: str | None = None, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        # Sent only when set (LLM_REASONING_EFFORT), because not every OpenAI-compatible model accepts it.
        self.reasoning_effort = reasoning_effort
        self.max_retries = max_retries

    def _post(self, headers: dict, request: dict) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            last = attempt == self.max_retries
            try:
                response = httpx.post(f"{self.base_url}/chat/completions", headers=headers,
                                      timeout=self.timeout, json=request)
            except httpx.TransportError:  # connection dropped, timed out, DNS ...
                if last:
                    raise
                _sleep(_retry_delay(attempt, None))
                continue
            if response.status_code in RETRY_STATUSES and not last:
                _sleep(_retry_delay(attempt, response))
                continue
            response.raise_for_status()
            return response
        raise AssertionError("unreachable")

    # Reasoning models count hidden reasoning tokens against max_tokens. At 2,000, gemini-3.8-flash spent
    # ~1,900 on reasoning and the JSON was cut off. Only tokens actually generated are billed.
    def complete(self, system: str, prompt: str, max_tokens: int = 16000) -> LLMResponse:
        started = time.monotonic()
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        request = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort
        body = self._post(headers, request).json()  # latency_ms below includes any retry waits
        usage = body.get("usage") or {}
        choice = body["choices"][0]
        return LLMResponse(
            text=choice["message"]["content"] or "",
            model=self.model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=int((time.monotonic() - started) * 1000),
            stop_reason=choice.get("finish_reason"),
            cached_input_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0,
        )
