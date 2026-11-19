"""Reading the model's reply."""
import json
from pathlib import Path

import pytest

from ledgerline.extraction import ExtractionError, extract
from ledgerline.llm.base import LLMResponse
from ledgerline.llm.fake import CANNED_EXTRACTION, FakeClient

TRUNCATED = Path(__file__).parent / "fixtures" / "openai_compat_truncated_dev_001.json"


def use_client(monkeypatch, client) -> None:
    monkeypatch.setattr("ledgerline.extraction.get_client", lambda: client)


class _ReplayClient:
    """Replays fixed LLMResponses in order."""

    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)

    def complete(self, system: str, prompt: str, max_tokens: int = 16000) -> LLMResponse:
        return self.responses.pop(0)


def test_reply_wrapped_in_a_markdown_code_fence_is_read(monkeypatch, ref):
    # gemini-3.8-flash wraps its JSON like this; the starter skipped every document because of it.
    fenced = "```json\n" + json.dumps(CANNED_EXTRACTION, indent=2) + "\n```"
    use_client(monkeypatch, FakeClient([fenced, fenced]))
    data, _ = extract("INVOICE TEXT", ref)
    assert data["supplier_name"] == "Sitara Industrial Supplies Pvt. Ltd."


def test_extraction_makes_one_call(monkeypatch, ref):
    # The verification pass doubled time and cost. On the 24 dev documents a single pass got 287/288
    # fields right; the 2-document comparison with the verification pass showed no difference.
    client = FakeClient()
    use_client(monkeypatch, client)
    _, responses = extract("INVOICE TEXT", ref)
    assert len(client.calls) == 1
    assert len(responses) == 1


def test_reply_cut_off_at_the_token_limit_is_reported_as_such(monkeypatch, ref):
    body = json.loads(TRUNCATED.read_text(encoding="utf-8"))
    choice = body["choices"][0]
    recorded = LLMResponse(text=choice["message"]["content"], model=body["model"],
                           input_tokens=body["usage"]["prompt_tokens"],
                           output_tokens=body["usage"]["completion_tokens"], latency_ms=14353,
                           stop_reason=choice["finish_reason"])
    use_client(monkeypatch, _ReplayClient([recorded]))
    with pytest.raises(ExtractionError, match="cut off") as caught:
        extract("INVOICE TEXT", ref)
    assert caught.value.responses == [recorded]  # the paid call is not lost


def test_reply_that_is_not_json_is_an_extraction_error(monkeypatch, ref):
    use_client(monkeypatch, FakeClient(["Sure! Here is the invoice data you asked for."]))
    with pytest.raises(ExtractionError):
        extract("INVOICE TEXT", ref)
