"""Token pricing for the cost dashboard and the llm_calls table.

The starter's table held per-thousand-token prices under a per-million label, so every cost it recorded
was 1,000× too low (the dashboard's ₹15 against Anthropic's $165 for October). A model missing from the
table is now unpriced (None), not free.
"""
from __future__ import annotations

# USD per million tokens: (input, output, cached input read). None for the cache rate means "not known":
# cached tokens are then charged at the full input rate, which can only overstate the cost.
# Anthropic: published list prices (Nov 2026); Haiku 5.5's rate is for prompts up to 100K tokens.
# google/gemini-3.8-flash: the rates of the OpenAI-compatible provider used for this submission.
USD_PER_MTOK: dict[str, tuple[float, float, float | None]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, None),
    "claude-opus-4-5": (5.00, 25.00, None),
    "claude-sonnet-4-5": (3.00, 15.00, None),
    "gpt-4o-mini": (0.15, 0.60, None),
    "google/gemini-3.8-flash": (0.75, 3.75, 0.075),
    "fake": (0.0, 0.0, 0.0),  # the offline test client
}


def cost_usd(model: str, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> float | None:
    """input_tokens includes any cached ones. Returns None for a model whose price isn't known."""
    if model not in USD_PER_MTOK:
        return None
    input_price, output_price, cached_price = USD_PER_MTOK[model]
    cached = min(cached_input_tokens, input_tokens)
    cached_rate = input_price if cached_price is None else cached_price
    usd_micro = (input_tokens - cached) * input_price + cached * cached_rate + output_tokens * output_price
    return usd_micro / 1_000_000
