# How I worked with AI

## Tools and models

- **Coding assistant:** Claude Code in the VS Code extension, with Claude Opus 5.5
- **Ledgerline's LLM:** `google/gemini-3.8-flash` through Perplexity's OpenAI-compatible API, with `LLM_REASONING_EFFORT=low`. It costs $0.75 / $3.75 per million input / output tokens, and $0.075 for cached input; I use ₹88 to the dollar. I didn't run Meridian's current model (Opus) or any other model.

## How I set up context

- **`CLAUDE.md`** (commit `45d56d5`) holds the rules I wanted on every change:
  - don't edit `FIRST_HOUR.md`, and never touch `AP_POLICY.md`;
  - every fix gets a test that fails before it;
  - tests pass offline with `LLM_PROVIDER=fake`;
  - small changes, no rewrites;
  - show me the diff before any commit;
  - no Co-Authored-By lines.
- **Read-only first.** In the first session I told it not to edit or create anything (`00_first_hour.md:96`). I had it walk one document through the pipeline (`00_first_hour.md:360`) before I wrote `FIRST_HOUR.md` myself.
- **The brief and the policy came from the repository, not pasted in.** It read `docs/` itself, and when a check was in question I pointed it at the section of `AP_POLICY.md`.
- **No plan mode.** I worked in small steps instead: findings first, then one fix at a time, each proposed, tested and approved. 
- **Memory.** One note, saved in session 3: don't edit the sections I have to write myself, even for typos.

## My workflow

I chose what to work on and in what order. The AI read the code, ran things, proposed fixes and wrote them. This is how I checked its work:

- **Tests first.** Every fix came with a test that failed before it and passed after it, and I asked to see the failure.
- **Diffs before commits.** I read each diff before approving a commit.
- **Paid runs only when I said so, and one document first.** When the starter failed on every document, I had it try a single document before going any further (`01_baseline_and_fixes.md:430`).
- **Evidence on disk.** Every real-model run is saved under `submission/runs/<commit>/` with its log, and scored by the same scripts (`score_predictions.py`, `compare_runs.py`). Code changes were also checked by replaying recorded model replies offline (`replay_recorded.py`), which costs nothing.
- **I checked the UI myself.** For the approval and XSS fixes, it started the app with the fake client and gave me test steps, and I ran them in my browser (`01_baseline_and_fixes.md:6201–6285`).
- **Writing.**
  - The AI drafted `FINDINGS.md`, `EVAL_REPORT.md`, and the Architecture and Policy changes sections of `DECISIONS.md`. I edited them.
  - I wrote `FIRST_HOUR.md`, `RULINGS.md`, the stakeholder replies and `REFLECTION.md`. For the replies, the AI only gathered the facts and gave me outlines.
  - I wrote the Part 4 section from an AI draft.

## Where the AI was wrong

1. **It called the date bug "latent", and I agreed** (`01_baseline_and_fixes.md:7170–7203`).
   - The model returned ISO dates, so the month-first date parsing never fired, and the AI listed the bug as latent. I moved it to "found but not fixed".
   - Ruling on `disp_02` showed that was a mistake (`02_rulings.md:225–230`). The prompt asks the model to copy dates as printed, and `02/04/2026` read month first falls in the previous financial year. So a resend of an invoice that had already been paid would have gone through as ready.
   - I had it fixed test-first (`02_rulings.md:983`, commit `aa58720`). The obvious fix, `dateutil`'s day-first setting, would have broken ISO dates, and a test written before the fix caught that (`02_rulings.md:1249`).
2. **A broken script reported "no change"** (`02_rulings.md:726`).
   - Replaying recorded replies with the Part 2 flags on showed nothing changing. The cause was zsh passing both flags as one merged variable.
   - The AI spotted it a step later and re-ran with the variables set explicitly.
   - What I took from it: a clean "nothing changed" needs as much checking as a failure.
3. **The evaluation report described a run I didn't submit** (session 3).
   - The AI drafted `EVAL_REPORT.md` around run `d4eec74`, saying fields were "287/288 in all four runs".
   - When it regenerated the predictions in session 2, it updated the findings and rulings but not the report. The submitted files came from a fifth run: 286/288 and a p95 of 4.6 s.
   - It flagged this itself in session 3, after comparing the submitted predictions byte for byte with each saved run. I had the report changed to cite the final run (commit `8492336`).
4. **It said tests were missing when they weren't** (session 3).
   - It told me `RULINGS.md` promised tests for `disp_01`, `disp_03` and `disp_04` that didn't exist, after looking only in `test_rulings.py`.
   - The tests exist in `test_policy_checks.py`, and it had listed them itself in session 2 (`02_rulings.md:949–956`).
   - It found the contradiction while drafting this file, by re-reading the session 2 log.
5. **It edited text I'd written myself** (session 3).
   - After an ambiguous "It's fine, go ahead", it corrected the spelling in my stakeholder replies and tried to commit.
   - I stopped the commit. It put my wording back and saved a note not to do that again.


## What I deliberately didn't delegate, and why

- **The documents the brief wants in my own words:** `FIRST_HOUR.md`, `RULINGS.md`, the stakeholder replies and `REFLECTION.md`. They're where my judgment is being assessed.
- **The decisions that affect where money goes:** each ruling, which departures from the policy go behind flags, what to fix and what to leave, and choosing B for Part 4. The AI can argue for a choice, but it can't be accountable for a payment to a fraudster.
- **Spending and commits.** Every paid run and every commit waited for my yes.
- **Checking the UI.** I clicked through the approval and XSS fixes myself, because a test that reads the source isn't the same as watching the page.

## Time

From my commit times on 19 November:

- **First hour** (reading, then writing `FIRST_HOUR.md`): 06:52–08:43.
- **Part 1 fixes and the Part 3 runs:** 10:08–15:55.
- **Part 2 rulings and the date fix:** until 18:01.
- **Part 3 clean-up, Parts 4 and 5, and `DECISIONS.md`:** 18:01–19:17.

Acutal hours worked ~7 hours

## Transcripts

- `00_first_hour.md`: Part 0, read-only exploration.
- `01_baseline_and_fixes.md`: the baseline runs, the Part 1 fixes, the Part 3 runs, and drafting the findings and the evaluation report.
- `02_rulings.md`: Part 2, the two flags and the date fix.

I checked the saved logs for API keys and found none.
