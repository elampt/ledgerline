"""Offline evidence for FINDINGS.md F1-F3, using the unmodified starter code.

No network: the LLM is replaced by the starter's own FakeClient. Where a document's fields are
needed, the fake returns a correct, hand-transcribed extraction of that document, so what is
shown is the starter's own routing, checks and approval logic, not model error.

Run from backend/ with the virtualenv:
    LLM_PROVIDER=fake OPENAI_API_KEY= ANTHROPIC_API_KEY= .venv/bin/python ../submission/baseline/offline_evidence.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

assert os.environ.get("LLM_PROVIDER") == "fake", "run with LLM_PROVIDER=fake"

from fastapi.testclient import TestClient  # noqa: E402

import ledgerline.extraction as extraction  # noqa: E402
from ledgerline import db  # noqa: E402
from ledgerline.api import app  # noqa: E402
from ledgerline.llm.fake import CANNED_EXTRACTION, FakeClient  # noqa: E402
from ledgerline.parsing import parse_date  # noqa: E402
from ledgerline.pipeline import process_document  # noqa: E402
from ledgerline.reference import load_reference  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DEV = REPO / "data" / "invoices" / "dev"
TMP = Path(tempfile.mkdtemp(prefix="ledgerline-evidence-"))


def use_replies(*replies: dict) -> None:
    """Every pipeline run makes two LLM calls (extract, verify); return the given reply for both."""
    queued = [json.dumps(r) for r in replies for _ in range(2)]
    client = FakeClient(queued)
    extraction.get_client = lambda: client


def show(label: str, inv: dict) -> None:
    print(f"  {label}: status={inv['status']} needs_review={inv['needs_review']} "
          f"review_reasons={inv['review_reasons']} warnings={inv['warnings']} "
          f"required_approvals={inv['required_approvals']}")


# Correct extractions, transcribed from the documents. The model's routing answer is "ready".
DEV_024 = {  # Sitara invoice; account number differs from vendor master, IFSC is the same
    "document_type": "invoice", "supplier_name": "Sitara Industrial Supplies Pvt. Ltd.",
    "supplier_gstin": "27AAKCS4821M1ZW", "invoice_number": "SIS/26-27/0051", "invoice_date": "28/04/2026",
    "currency": "INR", "subtotal": "11,100.00", "cgst": "999.00", "sgst": "999.00", "igst": "0.00",
    "round_off": "0.00", "total": "13,098.00", "bank_account": "50200012349999", "ifsc": "ZEPH0001234",
    "po_number": "PO-2026-0133", "notes": "",
    "line_items": [
        {"description": "Spring Washer M10 (Pkt/500)", "quantity": "10", "unit_price": "620.00", "amount": "6,200.00"},
        {"description": "SS Hex Nut M10 (Box/200)", "quantity": "5", "unit_price": "980.00", "amount": "4,900.00"},
    ],
    "requires_review": False, "review_reasons": [],
}
DEV_015 = {  # Sitara invoice SIS/26-27/0018, already paid on 2026-04-22 per paid_invoices.csv
    "document_type": "invoice", "supplier_name": "Sitara Industrial Supplies Pvt. Ltd.",
    "supplier_gstin": "27AAKCS4821M1ZW", "invoice_number": "SIS / 26-27 / 0018", "invoice_date": "02/04/2026",
    "currency": "INR", "subtotal": "29,000.00", "cgst": "2,610.00", "sgst": "2,610.00", "igst": "0.00",
    "round_off": "0.00", "total": "34,220.00", "bank_account": "50200012345678", "ifsc": "ZEPH0001234",
    "po_number": "PO-2026-0098", "notes": "",
    "line_items": [
        {"description": "SS Hex Bolt M10x40 (Box/100)", "quantity": "20", "unit_price": "1,450.00",
         "amount": "29,000.00"},
    ],
    "requires_review": False, "review_reasons": [],
}

ref = load_reference()
vendor = next(v for v in ref.vendors if v["gstin"] == "27AAKCS4821M1ZW")

print("=" * 78)
print("F1: the model's requires_review is the routing decision; code checks are only warnings")
print("=" * 78)
conn = db.connect(str(TMP / "f1.db"))
use_replies(CANNED_EXTRACTION, CANNED_EXTRACTION)
text = (DEV / "dev_001.txt").read_text(encoding="utf-8")
show("dev_001, 1st upload", process_document(conn, ref, text, "dev_001"))
show("dev_001, 2nd upload", process_document(conn, ref, text, "dev_001"))
print("  -> the second copy of the same invoice is 'ready_for_approval'; 'duplicate' is only a warning.")

print()
print("=" * 78)
print("F2: approval endpoint (api.py approve_invoice)")
print("=" * 78)
os.environ["LEDGERLINE_DB"] = str(TMP / "f2.db")
api = TestClient(app)


def payments(invoice_id: int) -> int:
    c = sqlite3.connect(os.environ["LEDGERLINE_DB"])
    return c.execute("SELECT COUNT(*) FROM payments WHERE invoice_id = ?", (invoice_id,)).fetchone()[0]


def upload(name: str, reply: dict) -> dict:
    use_replies(reply)
    return api.post("/api/invoices", files={"file": (name, (DEV / name).read_bytes(), "text/plain")}).json()


inv = upload("dev_001.txt", CANNED_EXTRACTION)
for i in range(3):
    r = api.post(f"/api/invoices/{inv['id']}/approve", json={"user_id": "kavya.iyer", "note": ""}).json()
    print(f"  (a) approve #{i + 1} by kavya.iyer -> {r}")
print(f"  (a) payment rows for invoice {inv['id']} (₹{inv['total']:,.2f}): {payments(inv['id'])}")

big = dict(CANNED_EXTRACTION, total="6,00,000.00")
inv = upload("dev_001.txt", big)
print(f"  (b) invoice {inv['id']}: total ₹{inv['total']:,.2f}, required_approvals={inv['required_approvals']}")
for i in range(2):
    r = api.post(f"/api/invoices/{inv['id']}/approve", json={"user_id": "kavya.iyer", "note": ""}).json()
    print(f"  (b) approve #{i + 1} by kavya.iyer -> {r}")
print(f"  (b) payment rows: {payments(inv['id'])}  (one person satisfied a two-approval invoice)")

inv = upload("dev_001.txt", CANNED_EXTRACTION)
r = api.post(f"/api/invoices/{inv['id']}/reject", json={"user_id": "farhan", "note": ""}).json()
print(f"  (c) reject -> {r}")
r = api.post(f"/api/invoices/{inv['id']}/approve", json={"user_id": "kavya.iyer", "note": ""}).json()
print(f"  (c) approve after reject -> {r}; payment rows: {payments(inv['id'])}")

print()
print("=" * 78)
print("F3: bank-detail check compares IFSC only; duplicate check compares raw invoice numbers")
print("=" * 78)
conn = db.connect(str(TMP / "f3.db"))
print(f"  vendor master V0030 Sitara: account {vendor['bank_account']}, IFSC {vendor['ifsc']}")
print("  dev_024 prints:              account 50200012349999, IFSC ZEPH0001234")
use_replies(DEV_024)
show("dev_024", process_document(conn, ref, (DEV / "dev_024.txt").read_text(encoding="utf-8"), "dev_024"))
print("  -> no bank_details_changed, even as a warning. The only warning, tax_type_mismatch, is false:")
print("     the supplier is in Maharashtra (27) and correctly charged CGST+SGST.")
print()
paid = next(p for p in ref.paid_invoices if p["invoice_number"] == "SIS/26-27/0018")
print(f"  paid_invoices.csv: {paid['invoice_number']} dated {paid['invoice_date']}, "
      f"₹{float(paid['total']):,.2f}, paid on {paid['paid_on']}")
print("  dev_015 prints:    SIS / 26-27 / 0018 dated 02/04/2026, ₹34,220.00")
use_replies(DEV_015)
show("dev_015", process_document(conn, ref, (DEV / "dev_015.txt").read_text(encoding="utf-8"), "dev_015"))
print(f"  -> no duplicate warning. Also, parse_date('02/04/2026') = {parse_date('02/04/2026')} (policy: 2026-04-02).")
