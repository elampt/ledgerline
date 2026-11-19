"""Part 2: Ledgerline behaves as submission/RULINGS.md rules on the disputed documents.

Rulings that depart from AP_POLICY.md are behind LEDGERLINE_FLAG_<NAME>=1, off by default. Each document runs
through process_document on its real text, with the model's recorded extraction from
submission/predictions_disputed.jsonl.
"""
import json

import pytest

from ledgerline.config import get_settings
from ledgerline.llm.fake import CANNED_EXTRACTION, FakeClient
from ledgerline.pipeline import normalize, process_document
from ledgerline.validation import run_checks

DISPUTED = get_settings().data_dir / "invoices" / "disputed"


def process(conn, ref, monkeypatch, document_id: str, extraction: dict) -> dict:
    monkeypatch.setattr("ledgerline.extraction.get_client", lambda: FakeClient([json.dumps(extraction)]))
    raw_text = next(DISPUTED.glob(f"{document_id}.*")).read_text(encoding="utf-8")
    return process_document(conn, ref, raw_text, document_id)


# --- disp_02: a "revised" invoice with the number and date of SIS/26-27/0018, paid on 2026-04-22 ---------

DISP_02 = {
    "document_type": "invoice", "supplier_name": "Sitara Industrial Supplies Pvt. Ltd.",
    "supplier_gstin": "27AAKCS4821M1ZW", "invoice_number": "SIS/26-27/0018", "invoice_date": "2026-04-02",
    "currency": "INR", "subtotal": "30400.00", "cgst": "2736.00", "sgst": "2736.00", "igst": "0.00",
    "round_off": "0.00", "total": "35872.00", "bank_account": "50200012345678", "ifsc": "ZEPH0001234",
    "po_number": "PO-2026-0098", "notes": "",
    "line_items": [{"description": "SS Hex Bolt M10x40 (Box/100)", "quantity": "20", "unit_price": "1520.00",
                    "amount": "30400.00"}],
    "requires_review": True, "review_reasons": ["duplicate"],
}


def test_disp_02_with_the_flag_a_duplicate_needs_no_approvals(conn, ref, monkeypatch):
    monkeypatch.setenv("LEDGERLINE_FLAG_DUPLICATE_ZERO_APPROVALS", "1")
    result = process(conn, ref, monkeypatch, "disp_02", DISP_02)
    assert result["review_reasons"] == ["duplicate"]
    assert result["required_approvals"] == 0  # §4.4: it can't be approved, only rejected


def test_disp_02_without_the_flag_needs_one_approval_as_policy_4_1_says(conn, ref, monkeypatch):
    result = process(conn, ref, monkeypatch, "disp_02", DISP_02)
    assert result["review_reasons"] == ["duplicate"]
    assert result["required_approvals"] == 1


def test_disp_02_is_a_duplicate_even_when_the_model_copies_the_date_as_printed(conn, ref, monkeypatch):
    result = process(conn, ref, monkeypatch, "disp_02", DISP_02 | {"invoice_date": "02/04/2026"})
    assert result["invoice_date"] == "2026-04-02"  # 2 April, FY 2026-27, the same as the paid original
    assert result["review_reasons"] == ["duplicate"]


# --- disp_05: line 1 bills 4 × ₹3,850.00 as ₹15,950.00, and the total adds up to the printed amounts -------

DISP_05 = {
    "document_type": "invoice", "supplier_name": "Precision Gauges & Instruments",
    "supplier_gstin": "27AABFP2915E1ZK", "invoice_number": "PGI/26-27/018", "invoice_date": "2026-05-06",
    "currency": "INR", "subtotal": "24950.00", "cgst": "2245.50", "sgst": "2245.50", "igst": "0.00",
    "round_off": "0.00", "total": "29441.00", "bank_account": "0219201000751", "ifsc": "TALB0000219",
    "po_number": "PO-2026-0157", "notes": "",
    "line_items": [
        {"description": "Plug Gauge 20H7 Go/NoGo", "quantity": "4", "unit_price": "3850.00", "amount": "15950.00"},
        {"description": "Calibration service (per instrument)", "quantity": "6", "unit_price": "1500.00",
         "amount": "9000.00"},
    ],
    "requires_review": False, "review_reasons": [],
}


def test_disp_05_with_the_flag_a_line_that_is_not_quantity_times_rate_goes_to_review(conn, ref, monkeypatch):
    monkeypatch.setenv("LEDGERLINE_FLAG_LINE_AMOUNT_CHECK", "1")
    result = process(conn, ref, monkeypatch, "disp_05", DISP_05)
    assert result["needs_review"]
    assert result["review_reasons"] == ["line_amount_mismatch"]  # 4 × ₹3,850.00 is ₹15,400.00
    assert result["required_approvals"] == 1


def test_disp_05_without_the_flag_is_ready_as_policy_3_says(conn, ref, monkeypatch):
    result = process(conn, ref, monkeypatch, "disp_05", DISP_05)
    assert not result["needs_review"]
    assert result["review_reasons"] == []


@pytest.mark.parametrize("quantity, unit_price, expected", [
    ("4", "620.00", []),                        # dev_001's second line: 4 × ₹620.00 = ₹2,480.00
    ("4", "620.25", []),                        # ₹1.00 over: within the tolerance §3 gives the total
    ("4", "620.26", ["line_amount_mismatch"]),  # ₹1.04 over
    (None, None, []),                           # nothing to multiply, so nothing to check
])
def test_with_the_flag_each_line_must_be_quantity_times_rate_within_one_rupee(
        conn, ref, monkeypatch, quantity, unit_price, expected):
    monkeypatch.setenv("LEDGERLINE_FLAG_LINE_AMOUNT_CHECK", "1")
    second = {"description": "Spring Washer M10 (Pkt/500)", "quantity": quantity, "unit_price": unit_price,
              "amount": "2,480.00"}
    inv = normalize(CANNED_EXTRACTION | {"line_items": [CANNED_EXTRACTION["line_items"][0], second]})
    assert run_checks(conn, ref, inv) == expected
