"""Score a predictions_dev.jsonl against data/ground_truth/dev.jsonl, as the pipeline actually wrote it.

Unlike the starter's eval, it scores routing and approvals, counts failed documents as failures, and
works out cost from token counts (the starter prices models missing from its table at ₹0).

Usage:  python3 -I submission/runs/score_predictions.py <predictions_dev.jsonl> [input $/M] [output $/M]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIELDS = ["document_type", "supplier_name", "supplier_gstin", "invoice_number", "invoice_date", "currency",
          "subtotal", "cgst", "sgst", "igst", "total", "po_number"]  # the starter eval's 12 fields
USD_TO_INR = 88.0

preds = {}
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    preds[row["document_id"]] = row
price_in = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
price_out = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
labels = [json.loads(line) for line in (REPO / "data" / "ground_truth" / "dev.jsonl").read_text().splitlines()]


def norm(v) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v).strip().lower()


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, -(-len(ordered) * p // 100) - 1))] if ordered else 0.0


missed, extra, wrong_reasons, wrong_approvals, field_errors, errors = [], [], [], [], [], []
correct = 0
secs, cost = [], []
for lab in labels:
    did, exp = lab["document_id"], lab["expected"]
    got = preds.get(did)
    if got is None:
        errors.append(f"{did}: no line written")
        continue
    if "processing_error" in got["review_reasons"]:
        errors.append(did)
    for f in FIELDS:
        if norm(got.get(f)) == norm(exp.get(f)):
            correct += 1
        else:
            field_errors.append(f"{did}.{f}: got {got.get(f)!r}, expected {exp.get(f)!r}")
    if exp["needs_review"] and not got["needs_review"]:
        missed.append(f"{did} (expected {exp['review_reasons']})")
    if not exp["needs_review"] and got["needs_review"]:
        extra.append(f"{did} (got {got['review_reasons']})")
    if sorted(got["review_reasons"]) != sorted(exp["review_reasons"]):
        wrong_reasons.append(f"{did}: got {sorted(got['review_reasons'])}, expected {sorted(exp['review_reasons'])}")
    if got["required_approvals"] != exp["required_approvals"]:
        wrong_approvals.append(f"{did}: got {got['required_approvals']}, expected {exp['required_approvals']}")
    u = got["usage"]
    secs.append(u["latency_ms"] / 1000)
    cost.append((u["input_tokens"] * price_in + u["output_tokens"] * price_out) / 1e6 * USD_TO_INR)

needed = sum(lab["expected"]["needs_review"] for lab in labels)
print(f"documents: {len(labels)} labelled, {len(preds)} lines written, processing_error: {errors}")
print(f"needed review but routed ready (missed): {len(missed)}/{needed}")
for m in missed:
    print(f"  {m}")
print(f"routed to review without needing it (extra): {len(extra)}")
for e in extra:
    print(f"  {e}")
print(f"review reasons exactly right: {len(labels) - len(wrong_reasons)}/{len(labels)}")
for w in wrong_reasons:
    print(f"  {w}")
print(f"required_approvals right: {len(labels) - len(wrong_approvals)}/{len(labels)}")
for w in wrong_approvals:
    print(f"  {w}")
print(f"fields correct (failed documents count as wrong): {correct}/{12 * len(labels)} "
      f"= {correct / (12 * len(labels)):.1%}")
for e in field_errors:
    print(f"  {e}")
print(f"LLM time per document: p50 {pct(secs, 50):.1f} s, p95 {pct(secs, 95):.1f} s, max {max(secs):.1f} s")
if price_in or price_out:
    print(f"LLM cost per document at ${price_in}/${price_out} per M tokens, ignoring cache discounts: "
          f"mean ₹{sum(cost) / len(cost):.2f}, total ₹{sum(cost):.2f}")
