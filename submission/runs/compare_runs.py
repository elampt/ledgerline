"""Side-by-side Part 3 metrics for several predictions_dev.jsonl files, as a Markdown table.

Usage:  python3 -I submission/runs/compare_runs.py <label>=<predictions_dev.jsonl> ... [--price IN OUT]

- Routing: a document that needed review but was routed ready is a miss (the costly error); one routed to
  review without needing it is an extra review (about ₹85 of AP time, per the CFO).
- Field accuracy on the starter eval's 12 fields, two ways:
  "starter's way": failed documents dropped from the count, dev_001-003 included (their answers are in the
  starter's prompt as examples); "honest": failed documents count as wrong, dev_001-003 removed.
- Cost from token counts at the given $/M rates, before any cache discount (the starter did not record
  cached tokens), at ₹88/$. Time is LLM time per document, as recorded.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIELDS = ["document_type", "supplier_name", "supplier_gstin", "invoice_number", "invoice_date", "currency",
          "subtotal", "cgst", "sgst", "igst", "total", "po_number"]
LEAKED = {"dev_001", "dev_002", "dev_003"}  # pasted with their answers into every starter prompt
USD_TO_INR = 88.0

args = sys.argv[1:]
price_in, price_out = 0.75, 3.75
if "--price" in args:
    i = args.index("--price")
    price_in, price_out = float(args[i + 1]), float(args[i + 2])
    args = args[:i] + args[i + 3:]
runs = [a.split("=", 1) for a in args]
labels = {}
for line in (REPO / "data" / "ground_truth" / "dev.jsonl").read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    labels[row["document_id"]] = row["expected"]


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


def metrics(path: str) -> dict:
    preds = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        preds[row["document_id"]] = row
    failed = sorted(d for d in labels if d not in preds or "processing_error" in preds[d]["review_reasons"])
    needed = [d for d in labels if labels[d]["needs_review"]]
    missed = sorted(d for d in needed if d in preds and not preds[d]["needs_review"])
    extra = sorted(d for d in labels if not labels[d]["needs_review"] and d in preds and preds[d]["needs_review"])
    exact = sum(1 for d in labels if d in preds
                and sorted(preds[d]["review_reasons"]) == sorted(labels[d]["review_reasons"]))
    approvals = sum(1 for d in labels if d in preds
                    and preds[d]["required_approvals"] == labels[d]["required_approvals"])

    def field_score(doc_ids, count_failed: bool) -> tuple[int, int]:
        right = total = 0
        for d in doc_ids:
            if d in failed and not count_failed:
                continue
            total += len(FIELDS)
            if d in failed:
                continue
            right += sum(norm(preds[d].get(f)) == norm(labels[d].get(f)) for f in FIELDS)
        return right, total

    usage = [preds[d]["usage"] for d in labels if d in preds] or [
        {"llm_calls": 0, "latency_ms": 0, "input_tokens": 0, "output_tokens": 0}]  # a run that wrote nothing
    secs = [u["latency_ms"] / 1000 for u in usage]
    cost = [(u["input_tokens"] * price_in + u["output_tokens"] * price_out) / 1e6 * USD_TO_INR for u in usage]
    return {
        "failed": failed, "dropped": sum(1 for d in labels if d not in preds), "missed": missed, "needed": len(needed), "extra": extra, "exact": exact,
        "approvals": approvals, "starter_way": field_score(sorted(labels), count_failed=False),
        "honest": field_score(sorted(set(labels) - LEAKED), count_failed=True),
        "calls": sum(u["llm_calls"] for u in usage) / len(usage),
        "p50": pct(secs, 50), "p95": pct(secs, 95), "max": max(secs),
        "cost": sum(cost) / len(cost), "out_tokens": sum(u["output_tokens"] for u in usage) / len(usage),
    }


results = [(label, metrics(path)) for label, path in runs]
rows = [
    ("Documents that failed (processing_error)", lambda m: f"{len(m['failed'])} of 24"),
    ("**Needed review, routed ready (missed)**",
     lambda m: "n/a: no document was written, so none reached AP at all" if m["dropped"] == 24 else
     f"**{len(m['missed'])} of {m['needed']}** " + (f"({', '.join(m['missed'])})" if m["missed"] else "")),
    ("Routed to review without needing it (extra)", lambda m: f"{len(m['extra'])}"
                                                              + (f" ({', '.join(m['extra'])})" if m["extra"] else "")),
    ("Review reasons exactly right", lambda m: f"{m['exact']} of 24"),
    ("Required approvals right", lambda m: f"{m['approvals']} of 24"),
    ("Field accuracy, starter's way (failures dropped, leaked examples kept)",
     lambda m: f"{m['starter_way'][0]}/{m['starter_way'][1]} = {m['starter_way'][0] / m['starter_way'][1]:.1%}"
     if m["starter_way"][1] else "n/a (no document processed)"),
    ("Field accuracy, honest (failures count, dev_001-003 removed)",
     lambda m: f"{m['honest'][0]}/{m['honest'][1]} = {m['honest'][0] / m['honest'][1]:.1%}"),
    ("LLM calls per document", lambda m: f"{m['calls']:.1f}"),
    ("Output tokens per document (mean)", lambda m: f"{m['out_tokens']:,.0f}"),
    ("LLM time per document, p50 / p95 / max", lambda m: f"{m['p50']:.1f} s / {m['p95']:.1f} s / {m['max']:.1f} s"),
    (f"Cost per document (mean, ${price_in}/${price_out} per M, no cache discount)", lambda m: f"₹{m['cost']:.2f}"),
]
print("| Measure (24 labelled dev documents) | " + " | ".join(label for label, _ in results) + " |")
print("|---|" + "---|" * len(results))
for name, fmt in rows:
    print(f"| {name} | " + " | ".join(fmt(m) for _, m in results) + " |")
