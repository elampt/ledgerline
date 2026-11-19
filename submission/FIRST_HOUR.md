# My first hour

_Under about 300 words, in your own words. Commit it on its own, before any commit that touches `backend/` or `frontend/`, and don't edit it afterwards. Save the AI sessions from this stretch in `ai-logs/` with a name starting `00_first_hour`. Being wrong here is fine._

## What I think is going on
From my project walkthrough, I am able to understand that the current system extracts the information from invoices using LLM, validates it against the company policies, finally routes the invoices for approval. But the main concern with the system is that it appears to completely rely on the model for decisions which should actually be taken by deterministic backend checks. I'll leave the UI cosmetic changes and optimizing the performance for now

## The risks I suspect, most serious first
1. Incorrect payment decisions as the routing is controlled by the model and validations are also only warnings
2. Duplicate and unauthorized approvals
3. Bank fraud (The current verification is against the IFSC code only and not the bank account number), also the vendor identification is also weak
4. The vendor bank details may unnecessarily be exposed to the LLM

## My plan for the time I have

I'll first trace the complete incoice workflow, right from extraction, validation, routing approval etc. My foremorst priorities would be to ensure determinisictic checks (Handling duplicate approvals, authorization etc.) for the decision and ensure that no invoice can go to payment without fulfilling the checks. Will focus on improvising the validation like bank-account matching, GST checks, duplicate detection, and that these validations actually influence the routing. 

## What I would ask Meridian

1. Apart from bank details, are there any other data from the invoice that are not supposed to be sent to the LLM ?
2. How should the system behave when extraction or validation fails ?