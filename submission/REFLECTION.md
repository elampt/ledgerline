# Reflection

_In your own words, about 20 minutes._

## Three things I didn't know when I started, and how I learned each one

1. Reasoning models spend hidden tokens, that's where both the cost and failures occured in my run
- A single run of dev_001 captured the raw reply, I found out that the model used 1,917 of 1,996 output tokens on reasoning alone, so the JSON was cut off. That's why the starter skipped every document on my first run
2. Masking has to cover the document also, not just the reference data
- Whhen I was trying to mask the bank account number present in the vendor master list, I suddenly realised tha the account number was present in the documents too
3. Errors can be because of missing data also, not purely because of the model
- Even with the starter's full reasoning and two passes, the model missed dev_015 (it was already paid) and dev_019 (it was sent earlier in the same batch). It never sees the payemnt history or the resto of the batch. No prompt or model can fix that, but the code check did it

## The decision I'm least sure of

Trusting a cheap model (budget constraints) with one pass and low reasoning (to restrict token usge), with the code checks as a saftey net

Why I made it:
1. 0 of 13 reviews missed in all thre runs where code decided routing
2. 99.2% field accuracy
3.₹0.61–0.65 a document, against a ₹1.50 budget.

Why I am doubtful:
1. It's only 13 documents, true miss rate could be up to about 21%
2. Checks run on whatever the model extracted, so a misread total, GSTIN or account number passes them.
3. It's a signle model from one provider


## With one more week

1. Real logins. The two-person rule depends on a user_id typed in the request directly, so one person can approve under two names
2. Measure Anthropic's models (Haiku 5.5 and Sonnet 5.5) on the dev set
3. Escalation and outage handling. Retry an unusable reply on a stronger model, add a fallback, set a time limit per document, and re-run failed documents.
4. Data minimisation - Stop spending the vendor master and the examples, figure out an alternate way