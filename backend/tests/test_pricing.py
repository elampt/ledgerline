"""LLM cost (the CTO's question): the dashboard said ₹15 for October, Anthropic billed about $165.

The starter's price table held per-thousand-token prices under a per-million label, so every cost was
1,000× too low, and any model missing from it was priced at ₹0.
"""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from ledgerline.api import app
from ledgerline.llm.fake import CANNED_EXTRACTION, FakeClient
from ledgerline.llm.openai_compat import OpenAICompatClient
from ledgerline.llm.pricing import cost_usd

RECORDED = Path(__file__).parent / "fixtures" / "openai_compat_truncated_dev_001.json"


@pytest.mark.parametrize("model, expected_usd", [
    ("claude-opus-5-5", 4.00 + 20.00),     # published list price per million input / output tokens
    ("claude-sonnet-5-5", 2.00 + 10.00),
    ("claude-haiku-5-5", 0.10 + 0.50),
    ("google/gemini-3.8-flash", 0.75 + 3.75),
])
def test_a_million_input_and_a_million_output_tokens_cost_the_list_price(model, expected_usd):
    assert cost_usd(model, 1_000_000, 1_000_000) == pytest.approx(expected_usd)


def test_cached_input_tokens_are_priced_at_the_cache_read_rate():
    # dev_001 on gemini-3.8-flash: 7,464 input tokens, 5,419 of them read from the provider's cache.
    expected = (2_045 * 0.75 + 5_419 * 0.075 + 416 * 3.75) / 1e6
    cost = cost_usd("google/gemini-3.8-flash", 7_464, 416, cached_input_tokens=5_419)
    assert cost == pytest.approx(expected)


def test_a_model_missing_from_the_table_is_unpriced_not_free():
    assert cost_usd("some-new-model", 10_000, 1_000) is None


def test_the_openai_compatible_client_reports_cached_input_tokens(monkeypatch):
    body = json.loads(RECORDED.read_text(encoding="utf-8"))

    recorded = httpx.Response(200, json=body, request=httpx.Request("POST", "https://example.invalid"))
    monkeypatch.setattr("ledgerline.llm.openai_compat.httpx.post", lambda url, **kwargs: recorded)
    response = OpenAICompatClient("https://example.invalid/v1", None, "m").complete("s", "p")
    assert (response.input_tokens, response.cached_input_tokens) == (7_464, 5_419)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGERLINE_DB", str(tmp_path / "api.db"))
    return TestClient(app)


def upload(api, monkeypatch, model: str):
    client = FakeClient([json.dumps(CANNED_EXTRACTION)], model=model)
    monkeypatch.setattr("ledgerline.extraction.get_client", lambda: client)
    return api.post("/api/invoices", files={"file": ("doc.txt", b"INVOICE TEXT", "text/plain")}).json()


def test_the_dashboard_reports_what_the_calls_cost(api, monkeypatch):
    invoice = upload(api, monkeypatch, "claude-opus-5-5")
    tokens = invoice["usage"]
    expected_inr = (tokens["input_tokens"] * 4.00 + tokens["output_tokens"] * 20.00) / 1e6 * 88.0
    stats = api.get("/api/stats").json()
    assert stats["llm_cost_inr"] == pytest.approx(expected_inr, abs=0.01)
    assert invoice["usage"]["cost_inr"] == pytest.approx(expected_inr, abs=0.0001)


def test_the_dashboard_says_when_some_calls_could_not_be_priced(api, monkeypatch):
    invoice = upload(api, monkeypatch, "some-new-model")
    assert invoice["usage"]["cost_inr"] is None
    assert api.get("/api/stats").json()["unpriced_llm_calls"] == 1
