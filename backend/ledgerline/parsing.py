"""Turn the strings the model copies off the page into Python values."""
from __future__ import annotations

import re
from datetime import date

from dateutil import parser as dateparser


def parse_amount(value) -> float | None:
    """'₹ 1,23,456.00' -> 123456.0"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("₹", "").replace("INR", "").replace(",", "").strip()
    return float(cleaned)


def parse_date(value, month_first: bool = False) -> date | None:
    """§1: Indian vendors print dates day first, US vendors month first. A date that starts with the year
    (2026-04-02, as the model usually returns it) is read year, month, day."""
    if not value:
        return None
    text = str(value).strip()
    year_first = re.match(r"\d{4}\D", text) is not None
    return dateparser.parse(text, dayfirst=not (month_first or year_first)).date()
