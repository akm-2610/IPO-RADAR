"""IPO alert eligibility rules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from models import IPO


def alert_rejection_reasons(ipo: IPO, today: date) -> list[str]:
    """Return every alert condition the IPO currently fails."""
    reasons: list[str] = []
    gmp_percent = ipo.gmp_percent
    if ipo.open_date is None:
        reasons.append("Open Date missing")
    elif ipo.open_date > today:
        reasons.append("IPO not yet open")
    if ipo.close_date is None:
        reasons.append("Close Date missing")
    elif ipo.close_date < today:
        reasons.append("IPO already closed")
    if ipo.qib_subscription is None:
        reasons.append("QIB subscription missing")
    elif ipo.qib_subscription <= Decimal("5"):
        reasons.append("QIB <= 5")
    if ipo.retail_subscription is None:
        reasons.append("Retail subscription missing")
    elif ipo.retail_subscription <= Decimal("2"):
        reasons.append("Retail <= 2")
    if ipo.overall_subscription is None:
        reasons.append("Overall subscription missing")
    elif ipo.overall_subscription <= Decimal("10"):
        reasons.append("Overall <= 10")
    if gmp_percent is None:
        reasons.append("GMP percentage unavailable")
    elif gmp_percent <= Decimal("20"):
        reasons.append("GMP <= 20%")
    return reasons


def matches_alert(ipo: IPO, today: date) -> bool:
    """Match only when every configured alert condition is strictly exceeded."""
    return not alert_rejection_reasons(ipo, today)
