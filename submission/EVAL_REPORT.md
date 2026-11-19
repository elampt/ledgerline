# Evaluation report

> **Draft.** `[TODO]` marks what is still to decide or check.

## Setup

- **Provider and model.** `google/gemini-3.8-flash`, through an OpenAI-compatible endpoint, at $0.75 / $3.75 per million input / output tokens ($0.075 for cached input).
- **Runs.** All on 19 November 2026. Rupee figures use the finance planning rate of ₹88 to the dollar.
- **Documents.**
  - The 24 labelled dev documents, of which 13 need review: 54%, against 13% in production (`PRODUCT_BRIEF.md`).
  - The 6 unlabelled disputed documents, which aren't scored here.
- **Three versions, same model:**
  - **Unmodified starter**, commit `45d56d5` (`baseline/`).
  - **Starter**, commit `2520a99` (`runs/starter_2520a99/`). This is the starter plus only the fix that lets it read the model's replies (F6), because unmodified it skips every document on this model. Everything else is the starter's own: two LLM calls per document, default reasoning, routing decided by the model, and its eval script.
  - **Mine**, the final run at commit `73e89a3` (`runs/73e89a3/`), which produced the submitted `predictions_dev.jsonl` and `predictions_disputed.jsonl`: one call per document, `reasoning_effort=low`, routing decided by the code's checks, bank account numbers masked in the prompt, dates read day first, and retries on rate limits. The dev set ran with the Part 2 flags off, so it follows `AP_POLICY.md` as written; the disputed set ran with them on. My earlier runs are compared under *How much to trust these numbers*.
- **Rate limits.** The provider rate-limited the starter's heavier traffic: `429 Too Many Requests` on 18 of 63 document attempts across its runs and re-runs. I re-ran the rate-limited documents twice, so the starter has two columns: **as run**, and **logic only**, with the re-run results. `dev_020` stayed rate-limited, so the logic-only column covers 23 of 24 documents. None of my five runs had a failed document. The first four were made before retries existed, so they weren't rate-limited at all. The final run had retries, which aren't logged, so it may have been rate-limited and recovered.

To reproduce, put the provider settings in `.env`, then:

```bash
# Mine (from the repository root, at 73e89a3 or later): dev with the Part 2 flags off, disputed with them on
export LLM_REASONING_EFFORT=low
cd backend
.venv/bin/python -m ledgerline.cli predict --input ../data/invoices/dev \
    --reference ../data/reference --output ../submission/predictions_dev.jsonl
LEDGERLINE_FLAG_DUPLICATE_ZERO_APPROVALS=1 LEDGERLINE_FLAG_LINE_AMOUNT_CHECK=1 \
    .venv/bin/python -m ledgerline.cli predict --input ../data/invoices/disputed \
    --reference ../data/reference --output ../submission/predictions_disputed.jsonl
cd .. && python3 -I submission/runs/compare_runs.py "mine=submission/predictions_dev.jsonl"

# Starter (commit 2520a99, in its own worktree, using the main virtualenv)
git worktree add ../ledgerline-2520a99 2520a99 && cd ../ledgerline-2520a99/backend
set -a && . ../../ledgerline/.env && set +a && export PYTHONPATH=$PWD
../../ledgerline/backend/.venv/bin/python -m ledgerline.cli predict --input ../data/invoices/dev \
    --reference ../data/reference --output starter_dev.jsonl
../../ledgerline/backend/.venv/bin/python eval/run_eval.py
```

## What the "94%" actually measured

`eval/run_eval.py` compares 12 extracted fields with the labels and reports the share that match. Four things are wrong with it as a measure of whether Ledgerline is safe to trust:

1. **It never looks at routing.** Whether a document that needed review was sent to review is the decision that moves money, and it isn't scored. Neither are approval counts, bank details or line items.
2. **Failed documents disappear.** A document that raises an error is printed as "skipping" and dropped from the denominator, so the more documents fail, the less the score falls.
3. **Three of the 24 test documents are in the prompt with their answers.** `dev_001`–`003` and their labels are pasted into every extraction prompt as examples.
4. **It can't produce a number on this model at all.** The unmodified starter skipped all 24 documents and then crashed with `ZeroDivisionError`.

**Reproduced on my model:** the starter (`2520a99`) running its own `run_eval.py` printed **`Field accuracy: 226/228 = 99.1%`**. Five of the 24 documents were rate-limited and silently dropped.

**Re-scored honestly.** Failed documents count as wrong, and `dev_001`–`003` are removed:

| Version | The starter's way | Failures counted | Failures counted, leaked examples removed |
|---|---|---|---|
| Starter, its own eval run | 99.1% (226/228) | 78.5% (226/288) | not computed¹ |
| Starter, as run (`predict`) | 99.6% (239/240) | – | **85.3%** (215/252) |
| Starter, logic only | 99.6% (275/276) | – | **94.8%** (239/252) |
| Mine | 99.3% (286/288) | – | **99.2%** (250/252) |

¹ The eval script doesn't save per-document results, so its leaked documents can't be separated out.

So the high field accuracy is real: the model reads invoices well. But it says almost nothing about safety. The starter's 99% sits alongside 2 of 13 reviews missed, which the eval never sees.

## What I chose to measure, and why

In order of importance to Meridian:

1. **Missed reviews:** documents that needed review but were routed as ready. The AP Lead: *"I can live with extra reviews. I can't live with a missed one."* One miss can mean paying a fraudster (₹3.8 lakh last quarter) or paying an invoice twice.
2. **Extra reviews:** routed to review without needing one. Each costs about ₹85 of AP time (CFO), and too many delay MSME payments past 45 days (Finance Controller).
3. **Review reasons exactly right.** A reviewer who sees the wrong reason checks the wrong thing.
4. **Required approvals right.** This is the two-person control on high-value and foreign-currency invoices.
5. **Documents that failed.** The output contract says none may be skipped. A failure must go to review as `processing_error`.
6. **Cost per document (₹), from the real token counts** at the provider's prices. This is before cache discounts, because the starter doesn't record cached tokens. My pipeline's real cost is a little lower.
7. **Time per document, p50 and p95, from the real calls.** This is LLM time only. Everything else in the pipeline takes milliseconds, but I didn't measure end to end.
8. **Field accuracy,** scored honestly as above.

## Starter versus mine, on the same model

24 labelled dev documents, `google/gemini-3.8-flash`. The full table, which also has my earlier run `d4eec74`, is in `runs/starter_2520a99/comparison.md`.

| Metric | Unmodified starter | Starter, as run | Starter, logic only | Mine |
|---|---|---|---|---|
| **Missed reviews (needed review, predicted ready)** | n/a: no document written | **2 of 13** | **2 of 13** (`dev_015`, `dev_019`) | **0 of 13** |
| **Cost per document (₹)** | (54 paid calls, nothing produced) | 3.04 | 3.53 | **0.61** |
| **Latency p50 and p95 (seconds)** | – | 46.9 / 67.3 | 48.6 / 67.3 | **3.5 / 4.6** |
| Extra reviews | – | 2 (rate limits) | 1 (rate limit) | 0 |
| Failed documents | 24 of 24 | 4 of 24 | 1 of 24 | 0 of 24 |
| Review reasons exactly right | 0 of 24 | 18 of 24 | 21 of 24 | **24 of 24** |
| Required approvals right | 0 of 24 | 17 of 24 | 20 of 24 | **24 of 24** |
| Field accuracy, honest | 0% | 85.3% | 94.8% | 99.2% |
| LLM calls per document | – | 2 | 2 | 1 |
| Output tokens per document | – | 7,066 | 8,233 | 434 |

Notes:

- **Why the starter misses those two.** Its misses are both duplicates. `dev_015` is a reprint of an invoice already paid. `dev_019` is the same invoice as `dev_006`, earlier in the batch. The model never sees the payment history or the rest of the batch, so no prompt or reasoning setting can fix this. My pipeline's code checks catch both.
- **What one pass and low reasoning cost me.** On its own, with one pass and low reasoning, the model also missed `dev_008`'s arithmetic (`experiments/latency_02_config_C_all_dev.log`). The code's totals check catches that too, so in my pipeline the cheaper setting costs nothing on routing.
- **Cost in production terms.**
  - **Starter on Opus:** the CTO's October bill works out to about ₹6 a document ($165 for about 2,400 documents).
  - **Mine:** at ₹0.61 a document (₹0.61–0.65 across my five runs), 3,000 documents a month come to about **₹1,830–1,950**, against a budget of ₹4,500 at ₹1.50.
- **Time.** p95 varies a lot from run to run: 4.6 seconds in the final run, but 8.3, 10.2, 10.3 and 10.5 seconds in the four runs before it. So treat it as at the 10-second target, not comfortably under it: 4.6 is the best of five. The slowest single document took 29.9 seconds for 405 output tokens, so the provider's response time causes the outliers, not the work.

## Labels I disagree with

- **`dev_015` `invoice_number`.**
  - **The disagreement:** the document prints `SIS / 26-27 / 0018`. The label has `SIS/26-27/0018`, but `OUTPUT_CONTRACT.md` asks for the invoice number "as printed", and that's what the model returned.
  - **If I'm right:** my field accuracy is 287/288 (99.7%); the other miss is `dev_019`, under *Failure analysis*. Routing is unaffected, because duplicate detection compares normalised numbers, so the document is still caught as a duplicate.

`[TODO: add any other label you disagree with, or say there are none]`

## Failure analysis

**Mine:** no routing errors on the dev set, and two field errors. One is the label question above. The other is real: on `dev_019` the model wrote `Konkan Tooling Pvt. Ltd.`, the spelling `dev_006`'s e-invoice uses, where the email prints `Konkan Tooling Pvt Ltd`. It happened in one of my five runs. Routing is unaffected, because vendors are matched by GSTIN, not by name. The remaining risks, ranked:

1. **Rate limits (provider).** The starter hit `429` on 18 of 63 attempts. My first four runs hit none, and were made before retries existed. The final run had retries, which aren't logged.
   - **The fix (commit `b26c33e`):** up to 3 retries with backoff, honouring `Retry-After`. After the last attempt the document still goes to review as `processing_error`.
   - **What hasn't been tested:** whether the retry works under a real rate limit, beyond the simulated `429`s in the tests.
2. **Injected instructions (rules and model).** `suspicious_content` is a code filter for markup and phrases aimed at AI or automation, with the model's own flag as a second layer. Only two dev documents test it. An injection phrased differently, and obeyed by the model, would get through to routing, unless another check catches the document, which F1's design ensures for every other rule.
3. **Latency (provider).** p95 is about 10 seconds with spikes to 30. Per document that's well within a nightly batch, but it's at the edge of the CTO's target.
4. **Date and amount parsing (normalisation, latent).** It didn't fire here, because the model returns ISO dates and plain numbers. It would fire with a model that copies the printed format (`FINDINGS.md`, *Found but not fixed*).

**Starter:** both missed reviews are a data problem, not an extraction problem: the model doesn't have the payment history or the batch. Its failed documents come from rate limits, and they're more likely because it sends about 2.5× as many tokens per document as mine: two passes with full reasoning.

## How much to trust these numbers

- **The sample is small.** Zero misses in 13 documents that needed review means the true miss rate is plausibly anywhere from 0 to about **21%** (one-sided 95% bound). The stronger evidence is structural: every §3 rule is now a code check with a test named after the document it reproduces, and the model can only add reasons, never remove them.
- **Stable across runs.**
  - **Fields:** 287/288 in the first four runs with these model settings, and 286/288 in the final run (`dev_019`'s supplier name, above).
  - **Routing:** 0 misses and 0 extra reviews in all three full runs since routing moved to code (`a3f51a3`, `d4eec74`, `73e89a3`), and in the replay of the recorded replies.
  - **Time** varied: p95 4.6–10.5 seconds, max 10.2–29.9 seconds.
  - **Cost** barely moved: ₹0.61–0.65 a document.
- **The starter's numbers depend on rate limiting.** Hence the two columns. One document (`dev_020`) never got a clean result.
- **One model and one provider.** I didn't run Opus, the model Meridian runs today, so these numbers don't show how the fixed pipeline performs on it.
- **What the dev set doesn't cover:**
  - production volumes and peaks (400 documents a day at month end);
  - vendors and payment history beyond the reference files;
  - noisier OCR, HTML emails and multi-page invoices;
  - more than one credit note and one foreign-currency invoice;
  - every way an injection can be phrased.

## My recommendation

**Yes, with conditions.** Put every invoice through Ledgerline next month, provided:

1. **The fixes already made stay in.** Routing decided by the code's checks; Approve safe to repeat; bank account numbers masked; real cost reporting.
2. **Before go-live:**
   - retry with backoff on rate limits (done: `b26c33e`);
   - real authentication, because the two-person rule now rests on a `user_id` typed into the request (`FINDINGS.md`);
   - the bank-change call-back decided with the Finance Controller.

   `[TODO: confirm which of these you'll have done]`
3. **Shadow review for the first month.** AP also checks a random 10% of the documents Ledgerline routes as ready: about 260 a month, roughly **₹22,000** of AP time.
4. **A daily check** of the `processing_error` count, p95 time and cost per document.

**How the recommendation weighs the two errors.**
- **The asymmetry:** one missed bank-change fraud (₹3.8 lakh) costs as much as about **4,500 extra reviews** at ₹85, and one missed duplicate at the median invoice (₹77,459) about 900.
- **What that means for the design:** it should prefer extra reviews whenever it's unsure, and it does. Failures, unknown dates and unknown totals all go to review.
- **What the dev set shows:** that bias cost nothing, with 0 extra reviews. In production, extra reviews will come mainly from rate-limit failures (fixed by retries) and from real but harmless matches.
- **Why the shadow sample is worth it:** its ₹22,000 is small next to a single missed fraud. It's the only way to measure the production miss rate that 13 dev examples can't.

**Evidence that would change my mind:**
- A missed review in the shadow sample of a kind a code check should have caught.
- More than about 2% of documents ending in `processing_error`, which would mean extra reviews and MSME payment delays.
- p95 time above 10 seconds for more than a few days.
- The DPO objecting to what is still sent to the provider: the vendor master without account numbers, and the policy text.
