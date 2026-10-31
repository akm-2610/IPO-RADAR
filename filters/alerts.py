"""IPO alert eligibility rules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from models import IPO


def alert_rejection_reasons(
    ipo: IPO,
    today: date,
    *,
    qib_threshold: Decimal = Decimal("5"),
    retail_threshold: Decimal = Decimal("2"),
    overall_threshold: Decimal = Decimal("10"),
    gmp_threshold_pct: Decimal = Decimal("20"),
) -> list[str]:
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
    elif ipo.qib_subscription <= qib_threshold:
        reasons.append(f"QIB <= {qib_threshold}")
    if ipo.retail_subscription is None:
        reasons.append("Retail subscription missing")
    elif ipo.retail_subscription <= retail_threshold:
        reasons.append(f"Retail <= {retail_threshold}")
    if ipo.overall_subscription is None:
        reasons.append("Overall subscription missing")
    elif ipo.overall_subscription <= overall_threshold:
        reasons.append(f"Overall <= {overall_threshold}")
    if gmp_percent is None:
        reasons.append("GMP percentage unavailable")
    elif gmp_percent <= gmp_threshold_pct:
        reasons.append(f"GMP <= {gmp_threshold_pct}%")
    return reasons


def matches_alert(ipo: IPO, today: date, **thresholds: Decimal) -> bool:
    """Match only when every configured alert condition is strictly exceeded."""
    return not alert_rejection_reasons(ipo, today, **thresholds)
