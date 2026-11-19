"""The interface every LLM provider client implements."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    stop_reason: str | None = None  # why the reply ended; "length" / "max_tokens" mean it was cut off
    cached_input_tokens: int = 0  # the part of input_tokens read from the provider's prompt cache


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> LLMResponse: ...
