"""OpenAI-compatible client, tested offline against a recorded provider response."""
import json
from pathlib import Path

import httpx
import pytest

from ledgerline.llm.openai_compat import OpenAICompatClient

# Recorded from google/gemini-3.8-flash on dev_001 with the starter's 2,000-token cap:
# finish_reason "length", 1,917 of 1,996 output tokens spent on reasoning, JSON cut off.
TRUNCATED = Path(__file__).parent / "fixtures" / "openai_compat_truncated_dev_001.json"
URL = "https://example.invalid/v1/chat/completions"


def _RecordedResponse(body: dict, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers, request=httpx.Request("POST", URL))


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


# --- retries: the provider rate-limited the starter on 18 of 63 document attempts (runs/starter_2520a99/) ---

@pytest.fixture
def provider(monkeypatch):
    """Answer each request with the next queued outcome: a status code, or an exception to raise."""
    recorded = json.loads(TRUNCATED.read_text(encoding="utf-8"))
    state = {"queue": [], "attempts": 0, "sleeps": []}

    def fake_post(url, **kwargs):
        state["attempts"] += 1
        outcome = state["queue"].pop(0) if state["queue"] else 200
        if isinstance(outcome, Exception):
            raise outcome
        status, headers = outcome if isinstance(outcome, tuple) else (outcome, None)
        return _RecordedResponse(recorded if status == 200 else {"error": "x"}, status, headers)

    monkeypatch.setattr("ledgerline.llm.openai_compat.httpx.post", fake_post)
    monkeypatch.setattr("ledgerline.llm.openai_compat._sleep",
                        lambda seconds: state["sleeps"].append(seconds))
    return state


def complete():
    return OpenAICompatClient("https://example.invalid/v1", None, "some-model").complete("s", "p")


def test_a_rate_limited_request_is_retried_until_it_succeeds(provider):
    provider["queue"] = [429, 429]
    assert complete().stop_reason == "length"  # the recorded response, on the third attempt
    assert provider["attempts"] == 3
    assert len(provider["sleeps"]) == 2


def test_a_server_error_is_retried(provider):
    provider["queue"] = [503]
    complete()
    assert provider["attempts"] == 2


def test_a_dropped_connection_is_retried(provider):
    provider["queue"] = [httpx.ConnectError("connection reset")]
    complete()
    assert provider["attempts"] == 2


def test_the_providers_retry_after_is_honoured(provider):
    provider["queue"] = [(429, {"retry-after": "7"})]
    complete()
    assert provider["sleeps"] == [7.0]


def test_it_gives_up_after_three_retries_and_the_error_reaches_the_batch(provider):
    # The batch then writes a processing_error line, so the document goes to review (F6).
    provider["queue"] = [429, 429, 429, 429]
    with pytest.raises(httpx.HTTPStatusError):
        complete()
    assert provider["attempts"] == 4


def test_a_request_the_provider_rejects_is_not_retried(provider):
    provider["queue"] = [400]
    with pytest.raises(httpx.HTTPStatusError):
        complete()
    assert provider["attempts"] == 1
