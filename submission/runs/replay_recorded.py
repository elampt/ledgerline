"""Replay recorded model replies through the current pipeline, offline. Costs nothing and makes no network calls.

The replies come from experiments/latency_02_config_C_all_dev.json: google/gemini-3.8-flash, one call per
document, reasoning_effort=low, and the same prompt the pipeline still uses. Each document goes through
process_document in document_id order on a fresh database, exactly as `make predict` would. Each line gets the
contract fields plus `_warnings`, the code checks' own result. Score the output with score_predictions.py.

Run from backend/ with the virtualenv:
    LLM_PROVIDER=fake .venv/bin/python ../submission/runs/replay_recorded.py \
        ../submission/experiments/latency_02_config_C_all_dev.json OUT.jsonl
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import ledgerline.extraction as extraction
from ledgerline import db
from ledgerline.cli import processing_error_line, to_contract
from ledgerline.llm.base import LLMResponse
from ledgerline.pipeline import process_document
from ledgerline.reference import load_reference

REPO = Path(__file__).resolve().parents[2]
recorded = {r["document_id"]: r["calls"][0] for r in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))}
out_path = Path(sys.argv[2])


class Replay:
    def __init__(self, call: dict):
        self.call = call

    def complete(self, system: str, prompt: str, max_tokens: int = 16000) -> LLMResponse:
        c = self.call
        return LLMResponse(c["text"], "google/gemini-3.8-flash", c["input_tokens"], c["output_tokens"],
                           c["latency_ms"], stop_reason=c["finish_reason"])


ref = load_reference(REPO / "data" / "reference")
conn = db.connect(str(Path(tempfile.mkdtemp(prefix="ledgerline-replay-")) / "replay.db"))
with open(out_path, "w", encoding="utf-8") as out:
    for path in sorted((REPO / "data" / "invoices" / "dev").iterdir()):
        call = recorded[path.stem]
        extraction.get_client = lambda call=call: Replay(call)
        try:
            invoice = process_document(conn, ref, path.read_text(encoding="utf-8"), path.stem, filename=path.name)
            line = to_contract(invoice) | {"_warnings": invoice["warnings"]}
        except Exception as exc:  # same as the batch: never drop a document
            line = processing_error_line(path.stem, getattr(exc, "responses", [])) | {"_warnings": [str(exc)]}
        out.write(json.dumps(line, ensure_ascii=False) + "\n")
print(f"replayed {len(recorded)} recorded replies to {out_path}")
