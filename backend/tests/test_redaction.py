"""AP policy §5.1 (F7): vendor bank account numbers must not be sent to the LLM provider.

Masking all but the last four digits is allowed. The full number comes back from the local document.
"""
import json
import re

import pytest

from ledgerline.config import get_settings
from ledgerline.extraction import build_extraction_prompt, extract
from ledgerline.llm.fake import CANNED_EXTRACTION, FakeClient
from ledgerline.pipeline import process_document

DOCS = sorted(p for d in ("dev", "disputed") for p in (get_settings().data_dir / "invoices" / d).iterdir())
LONG_DIGITS = re.compile(r"\d{9,}")


def sent_to_the_model(monkeypatch, ref, text: str, reply: dict | None = None) -> tuple[str, dict]:
    client = FakeClient([json.dumps(reply or CANNED_EXTRACTION)])
    monkeypatch.setattr("ledgerline.extraction.get_client", lambda: client)
    data, _ = extract(text, ref)
    return client.calls[0][1], data


def test_no_vendor_account_number_from_the_vendor_master_is_sent(ref):
    prompt = build_extraction_prompt("INVOICE TEXT", ref)
    leaked = [v["legal_name"] for v in ref.vendors if v["bank_account"] and v["bank_account"] in prompt]
    assert leaked == []


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_no_full_account_number_is_sent_for_any_document(ref, path):
    # Covers the document, the vendor master and the three example documents with their answers. The only
    # long digit run allowed is Meridian's own policy text: Appendix A's alphabet "0123456789ABC…".
    prompt = build_extraction_prompt(path.read_text(encoding="utf-8"), ref)
    allowed = set(LONG_DIGITS.findall(ref.policy_text))
    assert set(LONG_DIGITS.findall(prompt)) <= allowed


def test_the_last_four_digits_are_kept(ref, monkeypatch):
    text = "A/c No.   : 50200012349999\nIFSC : ZEPH0001234"
    prompt, _ = sent_to_the_model(monkeypatch, ref, text)
    assert "XXXXXXXXXX9999" in prompt


def test_an_account_number_printed_with_spaces_is_masked(ref, monkeypatch):
    prompt, _ = sent_to_the_model(monkeypatch, ref, "Bank A/c No: 5020 0012 3499 99, IFSC ZEPH0001234")
    assert "5020 0012 3499 99" not in prompt


def test_amounts_dates_gstins_and_ifsc_are_not_masked(ref, monkeypatch):
    text = ("GSTIN 27AAKCS4821M1ZW, IFSC ZEPH0001234, Invoice SIS/26-27/0051 dated 28/04/2026, "
            "TOTAL ₹ 1,23,45,678.00, TotInvVal 72275.0, Rs. 123456789.50")
    prompt, _ = sent_to_the_model(monkeypatch, ref, text)
    assert text in prompt


def test_the_full_account_number_is_restored_from_the_local_document(ref, monkeypatch):
    # The model can only copy what it was sent: the masked number. The full one comes from the original.
    text = (get_settings().data_dir / "invoices" / "dev" / "dev_024.txt").read_text(encoding="utf-8")
    reply = CANNED_EXTRACTION | {"bank_account": "XXXXXXXXXX9999"}
    _, data = sent_to_the_model(monkeypatch, ref, text, reply)
    assert data["bank_account"] == "50200012349999"


def test_dev_024_changed_account_is_still_caught_end_to_end(conn, ref, monkeypatch):
    text = (get_settings().data_dir / "invoices" / "dev" / "dev_024.txt").read_text(encoding="utf-8")
    reply = json.dumps(CANNED_EXTRACTION | {"bank_account": "XXXXXXXXXX9999",
                                            "invoice_number": "SIS/26-27/0051"})
    monkeypatch.setattr("ledgerline.extraction.get_client", lambda: FakeClient([reply]))
    invoice = process_document(conn, ref, text, "dev_024")
    assert invoice["bank_account"] == "50200012349999"
    assert "bank_details_changed" in invoice["review_reasons"]


def test_a_masked_number_that_cannot_be_restored_fails_closed(conn, ref, monkeypatch):
    # If the model returns a masked number that isn't in the document, the bank check sees only "1111",
    # which doesn't match the account on file, so the document goes to review.
    reply = json.dumps(CANNED_EXTRACTION | {"bank_account": "XXXXXXXXXX1111"})
    monkeypatch.setattr("ledgerline.extraction.get_client", lambda: FakeClient([reply]))
    invoice = process_document(conn, ref, "A/c No.   : 50200012345678", "doc")
    assert "bank_details_changed" in invoice["review_reasons"]
