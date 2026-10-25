from datetime import date
from decimal import Decimal

from main import format_alert
from filters.alerts import alert_rejection_reasons, matches_alert
from models import IPO


TODAY = date(2026, 10, 25)


def qualifying_ipo(**overrides):
    values = {
        "name": "Example IPO",
        "gmp": Decimal("25"),
        "issue_price": Decimal("100"),
        "qib_subscription": Decimal("5.01"),
        "retail_subscription": Decimal("2.01"),
        "overall_subscription": Decimal("10.01"),
        "open_date": date(2026, 10, 20),
        "close_date": TODAY,
    }
    values.update(overrides)
    return IPO(**values)


def test_alert_requires_all_conditions():
    assert matches_alert(qualifying_ipo(), TODAY)
    assert not matches_alert(qualifying_ipo(overall_subscription=Decimal("10")), TODAY)
    assert not matches_alert(qualifying_ipo(qib_subscription=Decimal("5")), TODAY)
    assert not matches_alert(qualifying_ipo(retail_subscription=Decimal("2")), TODAY)
    assert not matches_alert(qualifying_ipo(gmp=Decimal("20")), TODAY)
    assert alert_rejection_reasons(
        qualifying_ipo(retail_subscription=Decimal("2")), TODAY
    ) == ["Retail <= 2"]


def test_open_and_qualifying_ipo_matches():
    assert matches_alert(qualifying_ipo(), TODAY)


def test_ipo_not_yet_open_does_not_match():
    assert not matches_alert(qualifying_ipo(open_date=date(2026, 10, 26)), TODAY)


def test_ipo_already_closed_does_not_match():
    assert not matches_alert(qualifying_ipo(close_date=date(2026, 10, 24)), TODAY)


def test_ipo_opening_or_closing_today_is_inclusive():
    assert matches_alert(qualifying_ipo(open_date=TODAY), TODAY)
    assert matches_alert(qualifying_ipo(close_date=TODAY), TODAY)


def test_alert_skips_missing_issue_price_or_subscription():
    assert not matches_alert(qualifying_ipo(issue_price=None), TODAY)
    assert not matches_alert(qualifying_ipo(qib_subscription=None), TODAY)


def test_gmp_percentage_is_calculated_from_issue_price():
    ipo = qualifying_ipo(gmp=Decimal("20"))
    assert ipo.gmp_percent == Decimal("20")
    assert not matches_alert(ipo, TODAY)


def test_telegram_alert_format():
    ipo = qualifying_ipo()
    assert format_alert(ipo) == (
        "🚨 IPO ALERT\n\n"
        "IPO: Example IPO\n"
        "QIB: 5.01x\n"
        "Retail: 2.01x\n"
        "Overall: 10.01x\n"
        "GMP: 25.00%\n\n"
        "Open Date: 2026-10-20\n"
        "Close Date: 2026-10-25"
    )
