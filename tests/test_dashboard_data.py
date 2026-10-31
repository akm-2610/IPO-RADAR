from datetime import date
from decimal import Decimal

from dashboard_data import build_ipo_table
from models import IPO


def test_dashboard_shows_demand_for_each_ipo():
    records = [
        IPO(
            name="IPO One",
            qib_subscription=Decimal("5.5"),
            retail_subscription=Decimal("2.25"),
            overall_subscription=Decimal("10.75"),
            open_date=date(2026, 10, 30),
            close_date=date(2026, 11, 2),
        ),
        IPO(name="IPO Two"),
    ]

    table = build_ipo_table(records)

    assert len(table) == 2
    assert list(table["IPO"]) == ["IPO One", "IPO Two"]
    assert list(table["QIB Demand"]) == ["5.5x", "N/A"]
    assert list(table["Retail Demand"]) == ["2.25x", "N/A"]
    assert list(table["Overall Demand"]) == ["10.75x", "N/A"]
