# Rulings on the disputed documents

## My flags

The following flags are off by default and must be explicitly enabled when generating predictions_disputed.jsonl.

LEDGERLINE_FLAG_DUPLICATE_ZERO_APPROVALS=1: Sets the required approval count to zero for duplicate invoices. Applies to disp_02.

LEDGERLINE_FLAG_LINE_AMOUNT_CHECK=1: Checks quantity multiplied by unit price against the printed line amount. Applies to disp_05 and introduces the line_amount_mismatch review reason.

## disp_01

- **Ruling:** Needs review: `gstin_invalid`, `vendor_unknown`. One approval.
- **It rests on:** AP_POLICY §1 identifies domestic suppliers by GSTIN alone. Section 3 requires review for malformed GSTINs and unknown vendors. The printed GSTIN is malformed and does not match the vendor master. Matching bank details cannot establish identity.
- **The best argument against my ruling:** The document otherwise matches Sitara, including its name, bank account and IFSC. The incorrect character could be a scanning or printing error rather than an attempt at impersonation.
- **The policy change I'd propose, if any:** Define a controlled process for resolving near-matching GSTINs, requiring independent verification against the vendor master rather than automatic correction by the model.
- **Implemented?** Existing validation reasons cover this scenario. Add regression tests for malformed GSTINs and near matches.
- **Does my pipeline's line in `predictions_disputed.jsonl` match?** Yes. It produces both reasons and requires one approval.

## disp_02

- **Ruling:** Needs review: `duplicate`. Zero approvals; it must be rejected or resolved through a separately documented correction process.
- **It rests on:** AP_POLICY §3 defines duplicates using GSTIN, normalized invoice number and financial year. Section 4.4 explicitly prohibits approving duplicates. The original invoice has already been paid.
- **The best argument against my ruling:** This is marked REVISED and claims to supersede the original following a price revision. It may represent a legitimate additional liability rather than an attempt to collect twice.
- **The policy change I'd propose, if any:** Define a formal revised-invoice and debit-note workflow. Require a reference to the original invoice, independent supplier confirmation and approval of only the verified difference. Never silently replace a paid invoice.
- **Implemented?** Yes
- **Does my pipeline's line in `predictions_disputed.jsonl` match?** Partially. It detects the duplicate correctly, but reports one required approval instead of enforcing the rejection-only restriction. (the block was already enforced and only the count was wrong)

## disp_03

- **Ruling:** Needs review: `foreign_currency`. Two approvals.
- **It rests on:** AP_POLICY §1 classifies any invoice denominated in a currency other than INR as foreign. Section 4.1 requires two approvals. The USD amount is the invoice currency; printing an INR equivalent does not change that.
- **The best argument against my ruling:** This is an Indian GST-registered supplier with matching vendor and bank details. The INR equivalent is clearly printed, and the commercial agreement may already have been approved.
- **The policy change I'd propose, if any:** Clarify the treatment of foreign-currency invoices from domestic GST-registered suppliers, including exchange-rate sources, conversion dates, tax calculations and the authoritative payable amount.
- **Implemented?** No policy departure proposed. The existing foreign-currency rule should apply. Add a regression test confirming that foreign-currency invoices require two approvals.
- **Does my pipeline's line in `predictions_disputed.jsonl` match?** Yes. It identifies foreign currency and requires two approvals.

## disp_04

- **Ruling:** Ready, with no review reasons. One approval.
- **It rests on:** AP_POLICY §3 defines suspicious content as instructions directed at automated systems that attempt to influence checks or approval decisions. This message only requests an invoice reference in remittance advice. It does not ask the system to bypass controls or alter a decision.
- **The best argument against my ruling:** The note is explicitly addressed to an AP automation system. Treating machine-directed text as harmless could create a loophole for more subtle prompt injection.
- **The policy change I'd propose, if any:** Clarify that suspicious content must attempt to influence system behaviour, validation or approval. Ordinary operational instructions should not automatically trigger review.
- **Implemented?** No policy change required for this document. Add tests distinguishing harmless machine-directed text from instructions that manipulate approval decisions.
- **Does my pipeline's line in `predictions_disputed.jsonl` match?** Yes. It returns ready with no review reasons.

## disp_05

- **Ruling:** Needs review: `line_amount_mismatch`. One approval, after the discrepancy is resolved.
- **It rests on:** The current policy checks whether printed line amounts add up to the invoice total, but does not check quantity multiplied by unit price. The first line is overstated by ₹550, creating a ₹649 difference including GST.
- **The best argument against my ruling:** The printed line amount and invoice total agree. The discrepancy could be a legitimate pricing adjustment or a data-entry issue in the quantity or unit price.
- **The policy change I'd propose, if any:** Add a line-level arithmetic check with a defined rounding tolerance. Discrepancies should require supporting documentation or supplier clarification before payment.
- **Implemented?** Yes
- **Does my pipeline's line in `predictions_disputed.jsonl` match?** No. It returns ready because it checks invoice totals but ignores quantity multiplied by unit price.

## disp_06

- **Ruling:** Needs review: `future_dated_invoice`. One approval after the date discrepancy is resolved.
- **It rests on:** AP_POLICY §1 says to use the printed invoice date rather than the email date. However, the printed date is later than the document's receipt date and even later than the available data snapshot. The policy does not explicitly cover future-dated invoices.
- **The best argument against my ruling:** The printed date is authoritative under the existing policy, and the invoice may have been legitimately issued in advance. The email date alone does not establish fraud.
- **The policy change I'd propose, if any:** Introduce a future-date tolerance and require confirmation when an invoice date falls after its receipt date. Also clarify how the 90-day vendor-new rule applies to such invoices.
- **Implemented?** No. This requires a new validation check behind `LEDGERLINE_FLAG_FUTURE_DATED_INVOICE`. Add tests for future dates, ordinary invoices and the flag being disabled.
- **Does my pipeline's line in `predictions_disputed.jsonl` match?** No. It returns ready with no review reasons because future invoice dates are not currently checked.

## The two I consider riskiest, and why

**1. disp_02 – Revised invoice already paid**

This is the highest immediate financial risk. The original invoice has already been paid, but the revised document uses the same invoice number and date while requesting another payment. The existing duplicate detection catches it, and the API already refused to approve a duplicate, but the approval count was wrong. A date-parsing inconsistency could also let the duplicate check be bypassed: copied as printed, 02/04/2026 was read as 4 February, in the previous financial year. Both are now fixed: the count behind `LEDGERLINE_FLAG_DUPLICATE_ZERO_APPROVALS`, and the date reading with no flag, because AP_POLICY §1 already says Indian vendors print dates day first.

**2. disp_05 – Incorrect line amount**

This exposes a gap in the financial validation controls. The printed line amounts reconcile with the invoice total, but the first line is ₹550 higher than quantity multiplied by unit price. Including GST, the discrepancy is ₹649. The current validation checks only the final invoice total, so this error goes unnoticed. I would implement a line-level arithmetic check behind a feature flag and add regression tests for discrepancies and rounding tolerance.