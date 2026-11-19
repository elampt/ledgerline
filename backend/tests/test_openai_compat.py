"""OpenAI-compatible client, tested offline against a recorded provider response."""
import json
from pathlib import Path

import pytest

from ledgerline.llm.openai_compat import OpenAICompatClient

# Recorded from google/gemini-3.8-flash on dev_001 with the starter's 2,000-token cap:
# finish_reason "length", 1,917 of 1,996 output tokens spent on reasoning, JSON cut off.
TRUNCATED = Path(__file__).parent / "fixtures" / "openai_compat_truncated_dev_001.json"


class _RecordedResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._body


@pytest.fixture
def sent(monkeypatch):
    """Capture the request body and answer with the recorded response."""
    recorded = json.loads(TRUNCATED.read_text(encoding="utf-8"))
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs["json"])
        return _RecordedResponse(recorded)

    monkeypatch.setattr("ledgerline.llm.openai_compat.httpx.post", fake_post)
    return captured


def test_requests_room_for_reasoning_tokens(sent):
    # Reasoning models count hidden reasoning against max_tokens; 2,000 left ~80 tokens for the answer.
    OpenAICompatClient("https://example.invalid/v1", None, "some-model").complete("system", "prompt")
    assert sent["max_tokens"] >= 16000


def test_reports_why_the_reply_stopped(sent):
    client = OpenAICompatClient("https://example.invalid/v1", None, "some-model")
    assert client.complete("system", "prompt").stop_reason == "length"


def test_sends_reasoning_effort_when_configured(sent):
    # With one pass on the 24 dev documents, reasoning_effort=low gave p95 8.3 s and ₹0.62 per document,
    # against 42-57 s and ₹3.3-4.1 for the starter's settings on two of them.
    client = OpenAICompatClient("https://example.invalid/v1", None, "some-model", reasoning_effort="low")
    client.complete("s", "p")
    assert sent["reasoning_effort"] == "low"


def test_leaves_reasoning_effort_out_by_default(sent):
    # Not every OpenAI-compatible model accepts the parameter, so it is only sent when configured.
    OpenAICompatClient("https://example.invalid/v1", None, "some-model").complete("s", "p")
    assert "reasoning_effort" not in sent


def test_reasoning_effort_comes_from_the_environment(monkeypatch):
    from ledgerline.llm import get_client

    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    assert get_client().reasoning_effort == "low"
