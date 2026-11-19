"""AP policy §5.1: vendor bank account numbers must not be sent to external LLM providers.

Masking all but the last four digits is acceptable, so every account number in a prompt becomes, for example,
XXXXXXXXXX9999. The original document stays local, and the full number is restored from it after extraction.
"""
from __future__ import annotations

import csv
import io
import re

# Indian bank account numbers are 9 to 18 digits. A run that long, which isn't part of a decimal amount, is
# treated as one. That also masks e-invoice acknowledgement numbers, which extraction doesn't need.
_LONG_DIGITS = re.compile(r"(?<!\d)(?<!\d\.)\d{9,18}(?!\d)(?!\.\d)")
# An account number printed with spaces or hyphens, after a label such as "A/c No." or "Account".
_LABELLED = re.compile(r"(?i)\b(?:a/c|acc(?:ount)?|acct)\b[^\n\d]{0,30}(\d[\d \-]{7,28}\d)")


def mask_number(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    return "X" * max(len(digits) - 4, 0) + digits[-4:]


def mask_account_numbers(text: str) -> tuple[str, dict[str, str | None]]:
    """Mask account numbers in text. Returns the masked text and {masked: original as printed}; a masked
    form shared by two different numbers maps to None, so it is never restored to the wrong one."""
    originals: dict[str, str | None] = {}

    def mask(number: str) -> str:
        masked = mask_number(number)
        originals[masked] = number if originals.get(masked, number) == number else None
        return masked

    def mask_labelled(match: re.Match) -> str:
        if len(re.sub(r"\D", "", match.group(1))) < 9:
            return match.group(0)
        start = match.start(1) - match.start(0)
        return match.group(0)[:start] + mask(match.group(1))

    text = _LABELLED.sub(mask_labelled, text)
    text = _LONG_DIGITS.sub(lambda m: mask(m.group(0)), text)
    return text, originals


def mask_vendor_csv(vendors_csv: str) -> str:
    """The vendor master with its bank_account column masked (and any other long digit run)."""
    rows = list(csv.reader(io.StringIO(vendors_csv)))
    if rows and "bank_account" in rows[0]:
        column = rows[0].index("bank_account")
        for row in rows[1:]:
            if len(row) > column and row[column]:
                row[column] = mask_number(row[column])
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return mask_account_numbers(out.getvalue())[0]


def restore_account_number(value, originals: dict[str, str | None]):
    """Put back the full number for a masked one the model copied. Anything else is returned unchanged,
    so a masked number that can't be restored fails the bank check and goes to review."""
    if not isinstance(value, str):
        return value
    return originals.get(re.sub(r"\s", "", value).upper()) or value
