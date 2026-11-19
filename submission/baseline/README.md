# Baseline run of the unmodified starter

| | |
|---|---|
| Date | 2026-11-19, 04:39–04:51 UTC |
| Commit | `45d56d5` (no changes to `backend/`, `frontend/`, `data/`, `docs/` or `Makefile` since the initial commit `4525ce7`) |
| Provider | `LLM_PROVIDER=openai_compat` (Perplexity OpenAI-compatible endpoint) |
| Model | `google/gemini-3.8-flash` |
| Commands | `make predict`, then `make eval` |

## Files

- `predict.log`: stdout and stderr of `make predict`.
- `predictions_dev.jsonl`, `predictions_disputed.jsonl`: copies of what `make predict` wrote. Both are empty.
- `eval.log`: stdout and stderr of `make eval`.

## Result

| Run | Documents | Processed | Skipped | Wall time | Exit |
|---|---|---|---|---|---|
| `make predict` (dev) | 24 | 0 | 24 | 6m02s for both sets (about 12 s per document) | 0 |
| `make predict` (disputed) | 6 | 0 | 6 | (included above) | 0 |
| `make eval` (dev) | 24 | 0 | 24 | 4m53s (about 12 s per document) | 2 (`ZeroDivisionError`) |

Every document, in both runs, was skipped with the same error:

```
Expecting value: line 1 column 1 (char 0)
```

This is a `json.JSONDecodeError` from `json.loads(...)` in `backend/ledgerline/extraction.py`. The starter does not log the raw reply, so I diagnosed it afterwards on one document, `dev_001`, without changing any code.

## Diagnosis (one document, two extra calls)

- `diagnostic_dev_001.json`: the starter's own client and prompt builders, one extraction call. The reply was 176 characters, began with a Markdown code fence, and stopped mid-object. `json.loads` failed at character 0 on the first call, so the verification call never ran.
- `diagnostic_dev_001_raw.json`: the same request sent directly, keeping the full response body that the starter's client discards. Result: `finish_reason: "length"`, `completion_tokens: 1996` of which `reasoning_tokens: 1917`, and only 191 characters of visible content, again fenced and cut off.

Two separate causes, both on the first (extraction) call:

1. **Code fence.** The model wraps its JSON in a Markdown code fence. `json.loads` fails on the first character.
2. **Truncation.** The starter caps output at `max_tokens=2000` (`backend/ledgerline/llm/openai_compat.py`). This model spends about 1,900 of those on hidden reasoning, so the visible JSON is cut off after about 80 tokens. Stripping the code fence alone would still leave invalid JSON.

## What the run shows about the starter

- The batch skipped all 30 documents, wrote 0 lines, and still exited 0. `docs/OUTPUT_CONTRACT.md` says never to skip a document.
- `eval/run_eval.py` silently drops skipped documents from the denominator. With every document skipped, it crashes on `correct / total` and reports no accuracy at all.
- Each skipped document still made one paid LLM call, about 7.5k input and 2k output tokens. That's 54 calls over the two runs, plus the 2 diagnostic calls. (The single diagnostic call took 12–14 s, which matches the roughly 12 s per document in both runs, so each document most likely failed on its first call.) None were recorded, because the exception happens before `llm_calls` rows are written. The starter's own cost tracking would show ₹0 for this run.
