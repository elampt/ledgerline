"""Client for any OpenAI-compatible /chat/completions endpoint.

Works with OpenAI, Gemini's OpenAI-compatible endpoint, Groq, OpenRouter, vLLM and local
Ollama (OPENAI_BASE_URL=http://localhost:11434/v1, no key needed).
"""
from __future__ import annotations

import time

import httpx

from .base import LLMResponse


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str | None, model: str, timeout: float = 120.0,
                 reasoning_effort: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        # Sent only when set (LLM_REASONING_EFFORT), because not every OpenAI-compatible model accepts it.
        self.reasoning_effort = reasoning_effort

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
        response = httpx.post(f"{self.base_url}/chat/completions", headers=headers, timeout=self.timeout,
                              json=request)
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage") or {}
        choice = body["choices"][0]
        return LLMResponse(
            text=choice["message"]["content"] or "",
            model=self.model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=int((time.monotonic() - started) * 1000),
            stop_reason=choice.get("finish_reason"),
        )
