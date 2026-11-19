"""Deterministic checks for the review reasons in AP_POLICY.md section 3.

These decide routing (see pipeline.py). The model can add a reason they missed, but never remove one.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from decimal import Decimal

from .config import flag_enabled
from .models import Invoice
from .reference import ReferenceData

GSTIN_PATTERN = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]")
GSTIN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
BUYER_STATE_CODE = "27"  # Maharashtra. A string: it is compared with the first two characters of a GSTIN.
POLICY_CODES = frozenset({  # §3, the only review reasons Ledgerline may report
    "credit_note", "duplicate", "gstin_invalid", "vendor_unknown", "vendor_new", "bank_details_changed",
    "tax_type_mismatch", "totals_mismatch", "foreign_currency", "suspicious_content", "processing_error"})
TOTALS_TOLERANCE_PAISE = 100  # §3: a difference of exactly ₹1.00 is within tolerance
NEW_VENDOR_DAYS = 90
# §3 suspicious_content: markup that a browser would run, and text addressed to automated systems or AI.
SUSPICIOUS_MARKUP = re.compile(
    r"<\s*/?\s*(script|img|iframe|svg|object|embed|form|a)\b|\bon\w+\s*=|javascript:", re.IGNORECASE)
SUSPICIOUS_TEXT = re.compile(
    r"\b(ai assistants?|automated (invoice )?processing|language models?|llms?|requires_review|review_reasons"
    r"|ignore (all |any )?(previous|prior) instructions)\b", re.IGNORECASE)


def _paise(amount: float | None) -> int:
    return round((amount or 0.0) * 100)


def is_domestic(inv: Invoice) -> bool:
    """§1: a document in INR is domestic; any other currency is foreign."""
    return (inv.currency or "").strip().upper() == "INR"


def _name_key(name: str | None) -> str:
    """§1: a foreign supplier's legal name, compared case-insensitively, ignoring spaces and punctuation."""
    return re.sub(r"[^0-9a-z]", "", (name or "").lower())


def normalize_invoice_number(number: str | None) -> str:
    """§1: uppercase, with spaces and the characters / - # . removed. Leading zeros are significant."""
    return re.sub(r"[\s/\-#.]", "", number or "").upper()


def financial_year(d: date) -> int:
    """§1: 1 April to 31 March, identified by the year it starts in."""
    return d.year if d.month >= 4 else d.year - 1


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = GSTIN_ALPHABET.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return GSTIN_ALPHABET[(36 - total % 36) % 36]


def is_valid_gstin(gstin: str | None) -> bool:
    """Validate a GSTIN's format and check digit."""
    if not gstin:
        return False
    gstin = gstin.strip().upper()
    return GSTIN_PATTERN.fullmatch(gstin) is not None and gstin_checksum(gstin[:14]) == gstin[14]


def find_vendor(ref: ReferenceData, inv: Invoice) -> dict | None:
    """§1: a domestic supplier is identified by GSTIN alone (the printed name is not proof of identity);
    a foreign supplier by its supplier key."""
    if is_domestic(inv):
        gstin = (inv.supplier_gstin or "").strip().upper()
        return next((v for v in ref.vendors if gstin and v["gstin"].strip().upper() == gstin), None)
    key = _name_key(inv.supplier_name)
    return next((v for v in ref.vendors if key and _name_key(v["legal_name"]) == key), None)


def check_vendor(vendor: dict | None) -> list[str]:
    return [] if vendor else ["vendor_unknown"]


def check_vendor_new(inv: Invoice, vendor: dict | None) -> list[str]:
    if not vendor or not vendor.get("onboarded_on") or not inv.invoice_date:
        return []
    age = inv.invoice_date - date.fromisoformat(vendor["onboarded_on"])
    return ["vendor_new"] if age.days < NEW_VENDOR_DAYS else []


def check_gstin(inv: Invoice) -> list[str]:
    if is_domestic(inv) and not is_valid_gstin(inv.supplier_gstin):
        return ["gstin_invalid"]
    return []


def check_tax_type(inv: Invoice, buyer_state_code: str = BUYER_STATE_CODE) -> list[str]:
    if not is_domestic(inv) or not inv.supplier_gstin:
        return []
    intra_state = inv.supplier_gstin.strip()[:2] == buyer_state_code
    if intra_state and inv.igst > 0:
        return ["tax_type_mismatch"]
    if not intra_state and (inv.cgst > 0 or inv.sgst > 0):
        return ["tax_type_mismatch"]
    return []


def check_totals(inv: Invoice) -> list[str]:
    """§3: line amounts + CGST + SGST + IGST + round-off against the stated total, to the paisa."""
    if inv.total is None:
        return []
    computed = sum(_paise(item.amount) for item in inv.line_items) + sum(
        _paise(x) for x in (inv.cgst, inv.sgst, inv.igst, inv.round_off))
    return [] if abs(computed - _paise(inv.total)) <= TOTALS_TOLERANCE_PAISE else ["totals_mismatch"]


def check_line_amounts(inv: Invoice) -> list[str]:
    """RULINGS disp_05: each line's quantity × unit price against its printed amount, within the ₹1.00 that §3
    allows the total. A line without both a quantity and a unit price is not checked."""
    for item in inv.line_items:
        if item.quantity is None or item.unit_price is None:
            continue
        expected_paise = Decimal(str(item.quantity)) * Decimal(str(item.unit_price)) * 100
        if abs(expected_paise - _paise(item.amount)) > TOTALS_TOLERANCE_PAISE:
            return ["line_amount_mismatch"]
    return []


def _supplier_key(gstin: str | None, name: str | None, domestic: bool) -> str:
    return (gstin or "").strip().upper() if domestic and gstin else "name:" + _name_key(name)


def check_duplicate(conn: sqlite3.Connection, ref: ReferenceData, inv: Invoice,
                    org_id: str = "meridian") -> list[str]:
    """§3: same supplier key, normalized invoice number and FY, in the payment history or earlier in the
    batch. When either date is unknown the FY isn't compared, so a possible duplicate still goes to review."""
    if inv.document_type != "invoice":
        return []
    key = _supplier_key(inv.supplier_gstin, inv.supplier_name, is_domestic(inv))
    number = normalize_invoice_number(inv.invoice_number)
    if not number:
        return []
    fy = financial_year(inv.invoice_date) if inv.invoice_date else None

    def same(gstin, name, domestic, other_number, other_date) -> bool:
        other_fy = financial_year(date.fromisoformat(other_date)) if other_date else None
        return (_supplier_key(gstin, name, domestic) == key
                and normalize_invoice_number(other_number) == number
                and (fy is None or other_fy is None or fy == other_fy))

    earlier = conn.execute(
        "SELECT supplier_gstin, supplier_name, currency, invoice_number, invoice_date FROM invoices "
        "WHERE org_id = ? AND document_type = 'invoice'", (org_id,)).fetchall()
    if any(same(r["supplier_gstin"], r["supplier_name"], (r["currency"] or "").upper() == "INR",
                r["invoice_number"], r["invoice_date"]) for r in earlier):
        return ["duplicate"]
    # The payment history has no currency column: a row with a GSTIN is domestic, one without is foreign.
    if any(same(p["supplier_gstin"], p["supplier_name"], bool(p["supplier_gstin"]), p["invoice_number"],
                p["invoice_date"]) for p in ref.paid_invoices):
        return ["duplicate"]
    return []


def check_bank_details(inv: Invoice, vendor: dict | None) -> list[str]:
    """§3: account digits-only, IFSC case-insensitively. Not raised for an unknown vendor or none shown."""
    if not vendor:
        return []
    account = re.sub(r"\D", "", inv.bank_account or "")
    on_file = re.sub(r"\D", "", vendor.get("bank_account") or "")
    if account and on_file and account != on_file:
        return ["bank_details_changed"]
    ifsc, ifsc_on_file = (inv.ifsc or "").strip().upper(), (vendor.get("ifsc") or "").strip().upper()
    if ifsc and ifsc_on_file and ifsc != ifsc_on_file:
        return ["bank_details_changed"]
    return []


def check_credit_note(inv: Invoice) -> list[str]:
    return ["credit_note"] if inv.document_type == "credit_note" else []


def check_foreign_currency(inv: Invoice) -> list[str]:
    return [] if is_domestic(inv) else ["foreign_currency"]


def check_suspicious_content(raw_text: str) -> list[str]:
    suspicious = SUSPICIOUS_MARKUP.search(raw_text) or SUSPICIOUS_TEXT.search(raw_text)
    return ["suspicious_content"] if suspicious else []


def run_checks(conn: sqlite3.Connection, ref: ReferenceData, inv: Invoice, raw_text: str = "",
               org_id: str = "meridian") -> list[str]:
    vendor = find_vendor(ref, inv)
    return (
        check_credit_note(inv)
        + check_gstin(inv)
        + check_vendor(vendor)
        + check_vendor_new(inv, vendor)
        + check_tax_type(inv, str(ref.buyer.get("state_code") or BUYER_STATE_CODE))
        + check_totals(inv)
        + (check_line_amounts(inv) if flag_enabled("LINE_AMOUNT_CHECK") else [])
        + check_duplicate(conn, ref, inv, org_id)
        + check_bank_details(inv, vendor)
        + check_foreign_currency(inv)
        + check_suspicious_content(raw_text)
    )
