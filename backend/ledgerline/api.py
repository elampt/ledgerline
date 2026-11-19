"""HTTP API used by the reviewer UI.  Run: uvicorn ledgerline.api:app --reload"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db
from .config import USD_TO_INR, get_settings
from .pipeline import process_document
from .reference import load_reference

app = FastAPI(title="Ledgerline API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_conn():
    conn = db.connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_org(x_org_id: str = Header(default="meridian")) -> str:
    return x_org_id


class DecisionRequest(BaseModel):
    user_id: str
    note: str = ""


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/invoices")
async def upload_invoice(file: UploadFile, org_id: str = Depends(get_org), conn=Depends(get_conn)):
    raw_text = (await file.read()).decode("utf-8")
    document_id = (file.filename or "upload").rsplit(".", 1)[0]
    return process_document(conn, load_reference(), raw_text, document_id, org_id=org_id, filename=file.filename)


@app.get("/api/invoices")
def list_invoices(org_id: str = Depends(get_org), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, document_id, supplier_name, invoice_number, invoice_date, currency, total, status, "
        "needs_review FROM invoices WHERE org_id = ? ORDER BY id DESC",
        (org_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: int, conn=Depends(get_conn)):
    invoice = db.get_invoice(conn, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _audit(conn, invoice_id: int, action: str, body: DecisionRequest) -> None:
    """AP policy §4.7: who, when (the table's timestamp), which document, and the note."""
    conn.execute("INSERT INTO audit_log (invoice_id, action, user_id, note) VALUES (?, ?, ?, ?)",
                 (invoice_id, action, body.user_id.strip(), body.note))


def _decision_target(conn, invoice_id: int, body: DecisionRequest) -> dict:
    """Start a write-locked transaction and load the invoice, so concurrent clicks are taken one at a time."""
    if not body.user_id.strip():
        raise HTTPException(status_code=422, detail="user_id is required")
    conn.execute("BEGIN IMMEDIATE")
    invoice = db.get_invoice(conn, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.post("/api/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: int, body: DecisionRequest, conn=Depends(get_conn)):
    """AP policy §2 and §4. Safe to repeat: a second click or a retry changes nothing."""
    try:
        invoice = _decision_target(conn, invoice_id, body)
        if invoice["status"] == "rejected":
            raise HTTPException(status_code=409, detail="This document was rejected and can't be approved")
        if invoice["document_type"] == "credit_note":
            raise HTTPException(status_code=409, detail="Credit notes are never approved for payment")
        if "duplicate" in invoice["review_reasons"]:
            raise HTTPException(status_code=409, detail="A duplicate can't be approved; reject it instead")
        if invoice["status"] != "approved":
            if invoice["needs_review"] and not body.note.strip():
                raise HTTPException(status_code=422,
                                    detail="Add a note to approve a document that needed review")
            added = conn.execute(
                "INSERT OR IGNORE INTO approvals (invoice_id, user_id, note) VALUES (?, ?, ?)",
                (invoice_id, body.user_id.strip(), body.note)).rowcount
            if added:  # a repeat by the same person adds no approval and no log entry
                _audit(conn, invoice_id, "approve", body)
        approvals = conn.execute("SELECT COUNT(DISTINCT user_id) FROM approvals WHERE invoice_id = ?",
                                 (invoice_id,)).fetchone()[0]
        status = invoice["status"]
        # §4.3: every invoice needs at least one human approval, whatever required_approvals says.
        if status != "approved" and approvals >= max(1, invoice["required_approvals"]):
            status = "approved"
            conn.execute("UPDATE invoices SET status = 'approved' WHERE id = ?", (invoice_id,))
            conn.execute("INSERT OR IGNORE INTO payments (invoice_id, amount) VALUES (?, ?)",
                         (invoice_id, invoice["total"]))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"id": invoice_id, "approvals": approvals, "required_approvals": invoice["required_approvals"],
            "status": status}


@app.post("/api/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: int, body: DecisionRequest, conn=Depends(get_conn)):
    try:
        invoice = _decision_target(conn, invoice_id, body)
        if invoice["status"] == "approved":
            raise HTTPException(status_code=409, detail="Already approved: its payment instruction exists")
        if invoice["status"] != "rejected":  # rejecting twice changes nothing and logs nothing
            conn.execute("UPDATE invoices SET status = 'rejected' WHERE id = ?", (invoice_id,))
            _audit(conn, invoice_id, "reject", body)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"id": invoice_id, "status": "rejected"}


@app.get("/api/stats")
def stats(org_id: str = Depends(get_org), conn=Depends(get_conn)):
    """Feeds the cost dashboard."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT c.invoice_id) AS invoices, COALESCE(SUM(c.cost_usd), 0) AS cost_usd "
        "FROM llm_calls c JOIN invoices i ON i.id = c.invoice_id WHERE i.org_id = ?",
        (org_id,),
    ).fetchone()
    total_inr = row["cost_usd"] * USD_TO_INR
    return {
        "invoices_processed": row["invoices"],
        "llm_cost_inr": round(total_inr, 2),
        "avg_llm_cost_per_invoice_inr": round(total_inr / row["invoices"], 4) if row["invoices"] else 0.0,
    }
