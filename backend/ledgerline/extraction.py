"""Turn a raw vendor document into structured fields and a routing decision, using the LLM."""
from __future__ import annotations

import json
import re

from .config import get_settings
from .llm import LLMResponse, get_client
from .reference import ReferenceData

# The whole reply is one JSON object, optionally inside a single Markdown code fence. Anything else
# (prose, several blocks) is rejected rather than searched for something that looks like JSON.
_CODE_FENCE = re.compile(r"```(?:json)?[ \t]*\n(.*)\n[ \t]*```", re.DOTALL | re.IGNORECASE)
_CUT_OFF = {"length", "max_tokens"}  # OpenAI-compatible and Anthropic names for hitting the token limit


class ExtractionError(Exception):
    """The model's reply could not be used. Carries the calls already made, which were still paid for."""

    def __init__(self, message: str, responses: list[LLMResponse]):
        super().__init__(message)
        self.responses = responses

FIELDS = [
    "document_type", "supplier_name", "supplier_gstin", "invoice_number", "invoice_date", "currency",
    "subtotal", "cgst", "sgst", "igst", "round_off", "total", "bank_account", "ifsc", "po_number",
    "notes", "line_items",
]

SYSTEM_PROMPT = (
    "You are Ledgerline, an expert accounts-payable assistant for Meridian Precision Components "
    "Pvt. Ltd. You read vendor documents, extract their data and apply Meridian's AP policy."
)


def _few_shot_examples(limit: int = 3) -> str:
    """A few labelled examples so the model learns our exact output format."""
    data_dir = get_settings().data_dir
    blocks = []
    with open(data_dir / "ground_truth" / "dev.jsonl", encoding="utf-8") as f:
        for line in list(f)[:limit]:
            row = json.loads(line)
            doc = (data_dir / "invoices" / "dev" / row["filename"]).read_text(encoding="utf-8")
            blocks.append(f"DOCUMENT:\n{doc}\nOUTPUT:\n{json.dumps(row['expected'])}")
    return "\n\n".join(blocks)


def build_extraction_prompt(document_text: str, ref: ReferenceData) -> str:
    return f"""Read the vendor document below, extract its fields, and decide whether it needs human review under our AP policy.

AP POLICY:
{ref.policy_text}

VENDOR MASTER (CSV):
{ref.vendors_csv}

EXAMPLES:
{_few_shot_examples()}

Return a JSON object with these keys: {", ".join(FIELDS)}, requires_review (true/false) and review_reasons (list of policy codes).
Copy amounts and dates exactly as they are printed in the document.

{document_text}
"""


def _read_reply(response: LLMResponse, responses: list[LLMResponse]) -> dict:
    if response.stop_reason in _CUT_OFF:
        raise ExtractionError(f"model reply was cut off at the output token limit ({response.output_tokens} "
                              f"output tokens)", responses)
    text = response.text.strip()
    fenced = _CODE_FENCE.fullmatch(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"model reply is not valid JSON: {exc}", responses) from exc
    if not isinstance(data, dict):
        raise ExtractionError("model reply is not a JSON object", responses)
    return data


def extract(document_text: str, ref: ReferenceData) -> tuple[dict, list[LLMResponse]]:
    """One call. The starter's second "verification" pass doubled time and cost; on the dev set a single
    pass got 287/288 fields right (submission/experiments/latency_02_config_C_all_dev.log)."""
    client = get_client()
    responses = [client.complete(SYSTEM_PROMPT, build_extraction_prompt(document_text, ref))]
    return _read_reply(responses[0], responses), responses
