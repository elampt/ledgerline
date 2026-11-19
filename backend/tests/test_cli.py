"""The nightly batch command (docs/OUTPUT_CONTRACT.md)."""
import json

from ledgerline import cli
from ledgerline.llm.fake import CANNED_EXTRACTION, FakeClient


def test_unprocessable_document_is_written_for_review_not_skipped(tmp_path, monkeypatch):
    docs = tmp_path / "in"
    docs.mkdir()
    (docs / "doc_a.txt").write_text("first document", encoding="utf-8")
    (docs / "doc_b.txt").write_text("second document", encoding="utf-8")
    # doc_a: the model's first reply is not JSON. doc_b: two good replies.
    client = FakeClient(["I could not read this document.", json.dumps(CANNED_EXTRACTION),
                         json.dumps(CANNED_EXTRACTION)])
    monkeypatch.setattr("ledgerline.extraction.get_client", lambda: client)
    out = tmp_path / "predictions.jsonl"

    cli.main(["predict", "--input", str(docs), "--output", str(out), "--db", str(tmp_path / "batch.db")])

    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [line["document_id"] for line in lines] == ["doc_a", "doc_b"]
    failed, ok = lines
    assert failed["needs_review"] is True
    assert "processing_error" in failed["review_reasons"]
    assert failed["usage"]["llm_calls"] == 1  # the call that failed was still made, and paid for
    assert ok["needs_review"] is False
