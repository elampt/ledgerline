import json

from ledgerline.llm.fake import CANNED_EXTRACTION, FakeClient
from ledgerline.pipeline import process_document


def test_process_document_persists_invoice(conn, ref, fake_llm):
    invoice = process_document(conn, ref, "INVOICE TEXT", "doc_001", filename="doc_001.txt")
    assert invoice["supplier_name"] == "Sitara Industrial Supplies Pvt. Ltd."
    assert invoice["total"] == 23458.0
    assert invoice["invoice_date"] == "2026-04-25"
    assert invoice["status"] == "ready_for_approval"
    assert invoice["usage"]["llm_calls"] == 1


def test_document_text_reaches_the_model(conn, ref, fake_llm):
    process_document(conn, ref, "UNIQUE-MARKER-123", "doc_002")
    assert "UNIQUE-MARKER-123" in fake_llm.calls[0][1]


def test_line_items_are_stored(conn, ref, fake_llm):
    invoice = process_document(conn, ref, "INVOICE TEXT", "doc_003")
    assert [item["amount"] for item in invoice["line_items"]] == [17400.0, 2480.0]


def test_dev_014_us_vendor_date_copied_as_printed_is_read_month_first(conn, ref, monkeypatch):
    # §1: vendors whose country is US print MM/DD/YYYY. CloudNimbus prints 04/03/2026 for 3 April.
    reply = CANNED_EXTRACTION | {
        "supplier_name": "CloudNimbus Inc.", "supplier_gstin": None, "invoice_number": "CN-2026-04417",
        "invoice_date": "04/03/2026", "currency": "USD", "subtotal": "1298.00", "cgst": "0.00", "sgst": "0.00",
        "round_off": "0.00", "total": "1298.00", "bank_account": None, "ifsc": None, "po_number": None,
        "line_items": [{"description": "Team plan", "quantity": "25", "unit_price": "50.00", "amount": "1250.00"},
                       {"description": "API overage", "quantity": "12", "unit_price": "4.00", "amount": "48.00"}]}
    monkeypatch.setattr("ledgerline.extraction.get_client", lambda: FakeClient([json.dumps(reply)]))
    invoice = process_document(conn, ref, "INVOICE TEXT", "dev_014")
    assert invoice["invoice_date"] == "2026-04-03"
