"""Approving and rejecting (F2), against AP_POLICY.md sections 2 and 4, through the HTTP API."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from ledgerline.api import app
from ledgerline.llm.fake import CANNED_EXTRACTION, FakeClient


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGERLINE_DB", str(tmp_path / "api.db"))
    return TestClient(app)


@pytest.fixture
def upload(api, monkeypatch):
    """Upload a document whose extraction is dev_001 (clean, ₹23,458) with the given fields changed."""
    def _upload(**fields) -> dict:
        reply = json.dumps(CANNED_EXTRACTION | fields)
        monkeypatch.setattr("ledgerline.extraction.get_client", lambda: FakeClient([reply]))
        response = api.post("/api/invoices", files={"file": ("doc.txt", b"INVOICE TEXT", "text/plain")})
        assert response.status_code == 200
        return response.json()
    return _upload


def approve(api, invoice_id: int, user: str = "kavya.iyer", note: str = "checked"):
    return api.post(f"/api/invoices/{invoice_id}/approve", json={"user_id": user, "note": note})


def reject(api, invoice_id: int, user: str = "farhan.sheikh", note: str = "not ours"):
    return api.post(f"/api/invoices/{invoice_id}/reject", json={"user_id": user, "note": note})


def payments(invoice_id: int) -> int:
    import os

    with sqlite3.connect(os.environ["LEDGERLINE_DB"]) as conn:
        return conn.execute("SELECT COUNT(*) FROM payments WHERE invoice_id = ?", (invoice_id,)).fetchone()[0]


def test_one_approval_approves_a_clean_invoice_with_one_payment(api, upload):
    inv = upload()
    assert approve(api, inv["id"]).json()["status"] == "approved"
    assert payments(inv["id"]) == 1


def test_clicking_approve_three_times_creates_one_payment(api, upload):
    # Kavya: "When the system is slow, clicking Approve sometimes creates two payment entries."
    inv = upload()
    for _ in range(3):
        assert approve(api, inv["id"]).status_code == 200
    assert payments(inv["id"]) == 1  # §4.6: exactly one payment instruction


def test_concurrent_approvals_create_one_payment(api, upload):
    inv = upload()
    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(lambda _: approve(api, inv["id"]).status_code, range(6)))
    assert codes == [200] * 6
    assert payments(inv["id"]) == 1


def test_one_person_approving_twice_counts_once(api, upload):
    inv = upload(total="6,00,000.00", subtotal="5,08,474.58", cgst="45,762.71", sgst="45,762.71",
                 round_off="0.00", line_items=[{"description": "Press tooling", "quantity": "1",
                                                "unit_price": "5,08,474.58", "amount": "5,08,474.58"}])
    assert inv["required_approvals"] == 2
    approve(api, inv["id"], user="kavya.iyer")
    second = approve(api, inv["id"], user="kavya.iyer").json()
    # §4.2: one person approving twice counts once.
    assert (second["status"], second["approvals"], payments(inv["id"])) == ("ready_for_approval", 1, 0)
    third = approve(api, inv["id"], user="sunil.joshi").json()
    assert (third["status"], payments(inv["id"])) == ("approved", 1)


def test_a_rejected_invoice_cannot_be_approved(api, upload):
    inv = upload()
    assert reject(api, inv["id"]).status_code == 200
    assert approve(api, inv["id"]).status_code == 409
    assert payments(inv["id"]) == 0


def test_an_approved_invoice_cannot_be_rejected(api, upload):
    # Its payment instruction already exists; rejecting would leave the payment and say the opposite.
    inv = upload()
    approve(api, inv["id"])
    assert reject(api, inv["id"]).status_code == 409
    assert api.get(f"/api/invoices/{inv['id']}").json()["status"] == "approved"


def test_a_duplicate_cannot_be_approved_but_can_be_rejected(api, upload):
    upload()
    duplicate = upload()  # the same invoice again
    assert "duplicate" in duplicate["review_reasons"]
    assert approve(api, duplicate["id"]).status_code == 409  # §4.4
    assert payments(duplicate["id"]) == 0
    assert reject(api, duplicate["id"]).status_code == 200


def test_a_credit_note_cannot_be_approved_for_payment(api, upload):
    inv = upload(document_type="credit_note")
    assert approve(api, inv["id"]).status_code == 409  # §2: credit notes are never approved for payment
    assert payments(inv["id"]) == 0


def test_approving_a_document_that_needed_review_requires_a_note(api, upload):
    inv = upload(bank_account="50200012349999")  # dev_024: changed account number
    assert inv["needs_review"] is True
    assert approve(api, inv["id"], note="  ").status_code == 422  # §4.5
    assert approve(api, inv["id"], note="Called Sitara on the number on file; change confirmed.").json()[
        "status"] == "approved"
