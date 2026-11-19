from datetime import date

from ledgerline.parsing import parse_amount, parse_date


def test_parse_amount_indian_grouping():
    assert parse_amount("1,23,456.00") == 123456.0


def test_parse_amount_rupee_symbol():
    assert parse_amount("₹ 2,480.00") == 2480.0


def test_parse_amount_passes_numbers_through():
    assert parse_amount(1789.2) == 1789.2


def test_parse_amount_empty_is_none():
    assert parse_amount("") is None


def test_parse_date_iso():
    assert parse_date("2026-04-25") == date(2026, 4, 25)


def test_parse_date_with_slashes():
    assert parse_date("03/04/2026") == date(2026, 4, 3)  # §1: Indian vendors print dates day first


def test_parse_date_day_first_with_dashes_and_dots():
    assert parse_date("02-04-2026") == date(2026, 4, 2)
    assert parse_date("02.04.2026") == date(2026, 4, 2)


def test_parse_date_day_first_when_unambiguous():
    assert parse_date("25/04/2026") == date(2026, 4, 25)


def test_parse_date_iso_is_never_read_day_first():
    # dateutil's dayfirst=True alone turns 2026-04-02 into 4 February
    assert parse_date("2026-04-02") == date(2026, 4, 2)


def test_parse_date_month_first_for_us_vendors():
    assert parse_date("04/03/2026", month_first=True) == date(2026, 4, 3)  # §1: dev_014, CloudNimbus
