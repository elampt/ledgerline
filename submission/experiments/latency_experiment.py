"""Latency experiment: how much do reasoning effort and the verification pass cost in time and quality?

Sends the starter's own prompts (build_extraction_prompt, build_verification_prompt) straight to the
OpenAI-compatible endpoint in .env, so the full usage details (reasoning and cached tokens) are kept.
Changes no code. Prices are google/gemini-3.8-flash's, per million tokens.

Written against commit 2520a99, which still had the verification pass; it was removed after this
experiment. To re-run it, check that commit out (git worktree add ../ledgerline-2520a99 2520a99) and run
with PYTHONPATH set to that worktree's backend/, so its ledgerline package is imported.

Run from backend/ with the virtualenv:
    .venv/bin/python ../submission/experiments/latency_experiment.py OUT.json dev_001 dev_012
    .venv/bin/python ../submission/experiments/latency_experiment.py OUT.json --configs C all
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx
from dateutil import parser as dateparser

from ledgerline.config import USD_TO_INR, get_settings
from ledgerline.extraction import (SYSTEM_PROMPT, ExtractionError, _read_reply, build_extraction_prompt,
                                   build_verification_prompt)
from ledgerline.llm.base import LLMResponse
from ledgerline.reference import load_reference

USD_PER_MTOK = {"input": 0.75, "cached_input": 0.075, "output": 3.75}
CONFIGS = [
    {"name": "A", "label": "two passes, default reasoning (starter)", "passes": 2, "reasoning_effort": None},
    {"name": "B", "label": "two passes, reasoning_effort=low", "passes": 2, "reasoning_effort": "low"},
    {"name": "C", "label": "one pass, reasoning_effort=low", "passes": 1, "reasoning_effort": "low"},
]
FIELDS = ["document_type", "supplier_name", "supplier_gstin", "invoice_number", "invoice_date", "currency",
          "subtotal", "cgst", "sgst", "igst", "total", "po_number"]  # the starter eval's 12 fields
MONEY = {"subtotal", "cgst", "sgst", "igst", "total"}
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

out_path = Path(sys.argv[1])
args = sys.argv[2:]
if args[:1] == ["--configs"]:
    wanted = set(args[1].split(","))
    CONFIGS = [c for c in CONFIGS if c["name"] in wanted]
    args = args[2:]
s = get_settings()
assert s.llm_provider == "openai_compat", s.llm_provider
ref = load_reference()
labels = {}
for line in (s.data_dir / "ground_truth" / "dev.jsonl").read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    labels[row["document_id"]] = row
doc_ids = sorted(labels) if args == ["all"] else args
# Policy §1: vendors whose country is US print dates month first. Looked up from the label's supplier name.
US_VENDORS = {v["legal_name"].strip().lower() for v in ref.vendors if v.get("country") == "US"}


def call(prompt: str, effort: str | None) -> dict:
    body = {"model": s.llm_model, "max_tokens": 16000,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]}
    if effort:
        body["reasoning_effort"] = effort
    started = time.monotonic()
    resp = httpx.post(f"{s.openai_base_url.rstrip('/')}/chat/completions", timeout=180.0, json=body,
                      headers={"Authorization": f"Bearer {s.openai_api_key}"} if s.openai_api_key else {})
    ms = int((time.monotonic() - started) * 1000)
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}", "latency_ms": ms}
    b = resp.json()
    u = b.get("usage") or {}
    inp, out = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    cost = ((inp - cached) * USD_PER_MTOK["input"] + cached * USD_PER_MTOK["cached_input"]
            + out * USD_PER_MTOK["output"]) / 1e6
    return {"latency_ms": ms, "input_tokens": inp, "cached_tokens": cached, "output_tokens": out,
            "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "finish_reason": b["choices"][0].get("finish_reason"), "cost_inr": round(cost * USD_TO_INR, 3),
            "text": b["choices"][0]["message"].get("content") or ""}


def parsed(c: dict) -> dict:
    r = LLMResponse(c["text"], s.llm_model, c["input_tokens"], c["output_tokens"], c["latency_ms"],
                    stop_reason=c["finish_reason"])
    return _read_reply(r, [r])


def norm(field: str, v, month_first: bool = False):
    """Normalise properly (policy date order, lakh, ₹), so this measures the model, not the starter's parser."""
    if v is None or str(v).strip() == "":
        return ""
    t = str(v).strip()
    if field in MONEY:
        t = t.replace("₹", "").replace("Rs.", "").replace("INR", "").replace("USD", "").replace("$", "")
        t = t.replace(",", "").replace("/-", "").strip()
        lakh = t.lower().endswith("lakh")
        try:
            return f"{float(t[:-4]) * 100000 if lakh else float(t):.2f}"
        except ValueError:
            return t
    if field == "invoice_date":
        if ISO_DATE.fullmatch(t):
            return t
        try:
            return dateparser.parse(t, dayfirst=not month_first).date().isoformat()
        except (ValueError, OverflowError):
            return t
    return t.lower()


def score(data: dict, expected: dict) -> dict:
    us = str(expected.get("supplier_name") or "").strip().lower() in US_VENDORS
    wrong = [f for f in FIELDS if norm(f, data.get(f), us) != norm(f, expected.get(f), us)]
    return {"fields_correct": len(FIELDS) - len(wrong), "fields_wrong": {f: data.get(f) for f in wrong},
            "requires_review": data.get("requires_review"), "expected_review": expected["needs_review"],
            "review_reasons": sorted(data.get("review_reasons") or []),
            "expected_reasons": sorted(expected["review_reasons"])}


results = []
for doc_id in doc_ids:
    row = labels[doc_id]
    text = (s.data_dir / "invoices" / "dev" / row["filename"]).read_text(encoding="utf-8")
    for cfg in CONFIGS:
        run = {"document_id": doc_id, "config": cfg["name"], "label": cfg["label"], "calls": []}
        try:
            c1 = call(build_extraction_prompt(text, ref), cfg["reasoning_effort"])
            run["calls"].append(c1)
            if "error" in c1:
                raise ExtractionError(c1["error"], [])
            data = parsed(c1)
            if cfg["passes"] == 2:
                c2 = call(build_verification_prompt(text, data, ref), cfg["reasoning_effort"])
                run["calls"].append(c2)
                if "error" in c2:
                    raise ExtractionError(c2["error"], [])
                data = parsed(c2)
            run["result"] = score(data, row["expected"])
        except ExtractionError as exc:
            run["error"] = str(exc)
        ok = [c for c in run["calls"] if "error" not in c]
        run["total"] = {"latency_ms": sum(c["latency_ms"] for c in run["calls"]),
                        "output_tokens": sum(c["output_tokens"] for c in ok),
                        "reasoning_tokens": sum(c["reasoning_tokens"] or 0 for c in ok),
                        "cost_inr": round(sum(c["cost_inr"] for c in ok), 3)}
        results.append(run)
        t, r = run["total"], run.get("result")
        verdict = (f"fields {r['fields_correct']}/12, review {r['requires_review']} (expected "
                   f"{r['expected_review']}), reasons {r['review_reasons']} (expected {r['expected_reasons']})"
                   if r else f"ERROR {run['error']}")
        print(f"{doc_id} {cfg['name']} [{cfg['label']}]: {t['latency_ms'] / 1000:.1f} s, "
              f"{t['output_tokens']} out ({t['reasoning_tokens']} reasoning), ₹{t['cost_inr']:.2f} | {verdict}",
              flush=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def pct(values: list[float], p: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, -(-len(ordered) * p // 100) - 1))] if ordered else 0.0


print()
for cfg in CONFIGS:
    runs = [r for r in results if r["config"] == cfg["name"]]
    scored = [r for r in runs if "result" in r]
    secs = [r["total"]["latency_ms"] / 1000 for r in runs]
    needed = [r for r in scored if r["result"]["expected_review"]]
    missed = [r["document_id"] for r in needed if not r["result"]["requires_review"]]
    extra = [r["document_id"] for r in scored if not r["result"]["expected_review"] and r["result"]["requires_review"]]
    exact = [r for r in scored if r["result"]["review_reasons"] == r["result"]["expected_reasons"]]
    fields = sum(r["result"]["fields_correct"] for r in scored)
    print(f"{cfg['name']} [{cfg['label']}] over {len(runs)} documents")
    print(f"  failed (would be processing_error, so reviewed): {[r['document_id'] for r in runs if 'error' in r]}")
    print(f"  time per document: p50 {pct(secs, 50):.1f} s, p95 {pct(secs, 95):.1f} s, max {max(secs):.1f} s")
    print(f"  cost per document: mean ₹{sum(r['total']['cost_inr'] for r in runs) / len(runs):.2f}")
    print(f"  fields correct: {fields}/{12 * len(scored)} = {fields / (12 * len(scored)):.1%}" if scored else "")
    print(f"  needed review but routed ready (missed): {len(missed)}/{len(needed)} {missed}")
    print(f"  routed to review without needing it (extra): {len(extra)} {extra}")
    print(f"  review reasons exactly right: {len(exact)}/{len(scored)}")
