# Decisions

## Architecture

The model reads and the code decides. Each document gets one LLM call, which returns the invoice fields as JSON. Everything after that is code: it normalises dates and amounts, finds the vendor by GSTIN (never by the printed name), runs every §3 check, works out the approvals and routes the document. The model can still add a §3 reason the checks missed, but it can't remove one.

I moved routing into code because the model missed things no prompt can fix. On the dev set it let through `dev_015` (already paid, and it never sees the payment history), `dev_019` (a resend of an invoice earlier in the same batch) and `dev_008` (bad arithmetic). The code catches all three, and each check has a test named after the document that exposed it.

The prompt holds the AP policy, the vendor master, three worked examples and the document. The reply must be a single JSON object. Anything else, including a reply cut off at the token limit, counts as a failure, and a failed document goes to review as `processing_error` instead of being dropped. Approvals are enforced on the server, so a double-click or a retry can't create a second payment, and every decision is logged.

I treat every document as hostile. A document can't argue its way out of review, because the model can only add reasons. Markup and text aimed at AI are flagged as `suspicious_content`, and notes are shown as plain text, never as HTML. The model never sees a full account number, so it can't copy the one on file. What's not covered yet: a document that tricks the model into misreading a field could still pass the checks, the filter only knows phrases it has seen, and there's no login.

Only the LLM provider receives anything: the policy, the vendor master, the examples and the document, with every account number masked to its last four digits (§5.1). Under §5.2 the vendor master and examples probably shouldn't be sent now that code matches vendors, but I'd want a measured run before removing them.

## Part 4: what I went deep on, and why

I chose Option B: cost and reliability.

Two of the four rollout conditions in the product brief are keeping costs at ₹1.50 per document and p95 processing time under 10 seconds. Since these apply are applicable to every invoice, improvements here will help to boost operational efficiency

The starter implementation was significantly above both targets. The starter design measured ₹3.04–₹3.53 per document with a p95 of approximately 67 seconds. Provider rate limits also affected 18 of 63 document attempts. The initial design was expensive

After moving routing decisions into deterministic backend code, the model only needed to extract information it required. A single low-cost model pass achieved approximately 99.2% extraction accuracy, with measured costs of ₹0.61–₹0.65 per document across five runs. The code-controlled routing missed 0 of 13 review cases, compared with 3 misses when the model decided routing independently.

I did not choose Option A because its most important payment-safety elements were already addressed through Part 1: server-side approval enforcement, protection against duplicate approvals and an audit log. I did not identify an option C as well in the given time.


## Replies to stakeholders

### Anita Rao, CFO
What I did:
- Clean invoices correctly on dev set as ready, 0 of 13 reviews missed, and 0 extra reviews on the 11 clean documents
- Approve is one click now and is safe to double click
- LLM cost is ₹0.61–0.65 a document, about ₹1,900 a month, against about ₹18,000 at October's rate.

Not yet done:
- No-click approval. Policy §4.3 says every invoice needs a human approval, so it's Sunil's decision. Propose a flag, switched on only after a month's shadow check (about 260 documents, about ₹22,000)
- Auto-fixing GSTINs. The GSTIN is how we know who we're paying (§1). In disp_01 the name and bank details match Sitara but the GSTIN doesn't. Offer instead: Ledgerline suggests the correction and a reviewer confirms it.

### Farhan Sheikh, Head of AP
What I did:
- Double payments are fixed. Even 3 clicks now will give only 1 payment. One person approving twice also counts once, rejected and duplicate invoices can't be approved, there's an audit log
- Bank changes are now detected by account number as well, not just IFSC

Not yet done:
- Blocking bank change until a call back needs Sunil's phone field, which I'll propose to him

### Deepak Menon, CTO
What I did:
- The bill was right, but the dashboard was wrong. Per thousand prices were stored under per-million label, so the cost was 1,000x too low. Missing model prices also costed 0 Rupees, both are fixed now
- Outages are now handled with retries on rate limits
- LLM p95 of 4.6-10.5 seconds accross five runs (the starter's was 67)

Not yet done:
- Fine tuning since extraction isn't the problem, the misses came from missing data and arithmetic which the code now hanles


### Priya Natarajan, Data Protection Officer
What I did:
- Masked all except last four digits of the bank account number that is being passed to the LLM
- AP Policy text, vendor master, three example invoices, the document itself are sent to the LLM provider
- Regarding the other question asked, yes we were initially sending the full acount number to LLM, it is now fixed

Not yet done:
- Gaps: Account number split accross lines or written in words aren't caught yet


### Sunil Joshi, Finance Controller
What I did:
- No document is dropped anymore
- Retries cut the reviews caused by failures
- No policy changed. The two flags are off by default

Not yet done:
- When bank_details_changed triggers, Approve is refused until someone records callback
- That record goes in the audit log, second person has to approve

### Ravi Kulkarni, contractor
What I agree:
- Model reads pretty well accross OCR text, email and e-invoice JSON
- Policy is till in prompt
- I've removed the verification pass, it doubled the cost and there was no difference before and after

What I don't agree:
- Let the prompt and model decide the routing. When the model decided the routing, it missed reviews that no prompt can fix. With the model routing: 3 out of 13 missed. With the code routing, 0 got missed

## Policy changes I propose

These are proposals; I haven't changed `AP_POLICY.md`. Numbers 2 and 3 are built behind flags that are off by default. The rest aren't built.

1. **Call the vendor back before paying a changed bank account.** An invoice flagged `bank_details_changed` can't be approved until someone records a call to the vendor on the number in our vendor master: who called, when, and what the vendor confirmed. This is the workflow a phone-number field would serve, and it's the pattern behind last quarter's ₹3.8 lakh loss. It costs us collecting numbers for 38 vendors and a short wait on that vendor's payment.
2. **Give duplicates zero approvals, and revised invoices their own route** (`LEDGERLINE_FLAG_DUPLICATE_ZERO_APPROVALS`). Today §4.1 asks for an approval that §4.4 forbids. A revision like `disp_02` should cite the original and be confirmed with the supplier, and we pay only the difference. Genuine revisions get slower.
3. **Check each line's arithmetic** (`LEDGERLINE_FLAG_LINE_AMOUNT_CHECK`). Quantity × unit price should match the line amount within ₹1.00. `disp_05` overstates a line by ₹550 and still adds up to its total, so it passes today. Expect some extra reviews where vendors round prices; I'd measure how many before switching it on.
4. **Suggest a fix for a nearly-right GSTIN, never apply it.** If changing one misread character (O for 0, I for 1) gives a GSTIN in our vendor master, show that to the reviewer. It stays a review, because a mismatched GSTIN is what impersonation looks like (`disp_01`). The risk is reviewers accepting suggestions without checking.
5. **Auto-approve small, clean invoices, but only after a month of evidence.** Domestic, under ₹10,000, from a vendor we've paid before, no bank change, routed ready: about 1,040 invoices and ₹88,000 of AP time a month. A miss would be paid without anyone looking, so this needs real logins and a clean shadow month first (about 260 checks, ₹22,000).
6. **Narrow what counts as suspicious.** Count text that tries to change a check, the routing or an approval, plus embedded markup. As written, `disp_04`'s request to quote the invoice number in the remittance would go to review. A narrower rule leaves room for subtler tricks, but a document still can't talk its way out of a review.
7. **Review invoices dated after they arrived.** `disp_06` is dated after the email that brought it, and §1 tells us to trust the printed date. A new review reason would catch this, at the cost of a few extra reviews.
8. **Say what to pay on a USD invoice from an Indian supplier.** `disp_03` still needs two approvals. The policy should name the payable amount, and the exchange rate and date to use.
