from datetime import date
from decimal import Decimal

from parsing import parse_close_date, parse_issue_price, parse_open_date, parse_subscription


def test_parse_close_date_from_range():
    assert parse_close_date("29-2 Nov", date(2026, 10, 25)) == date(2026, 11, 2)


def test_parse_close_date_with_explicit_year():
    assert parse_close_date("October 23, 2026", date(2026, 10, 25)) == date(2026, 10, 23)


def test_parse_open_date_handles_shared_month_and_cross_month_ranges():
    assert parse_open_date("24-27 Oct", date(2026, 10, 25)) == date(2026, 10, 24)
    assert parse_open_date("29-2 Nov", date(2026, 10, 25)) == date(2026, 10, 29)


def test_parse_price_band_uses_upper_bound():
    assert parse_issue_price("₹78 to ₹82 per share") == Decimal("82")


def test_parse_subscription_percentage_as_multiplier():
    assert parse_subscription("250%") == Decimal("2.5")
    assert parse_subscription("5.2x") == Decimal("5.2")
