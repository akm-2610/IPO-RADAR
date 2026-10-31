"""IPO eligibility evaluation and dashboard-friendly metrics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from filters.alerts import alert_rejection_reasons
from models import IPO
from services.settings import RadarSettings


def rejection_reasons(ipo: IPO, today: date, settings: RadarSettings) -> list[str]:
    return alert_rejection_reasons(
        ipo,
        today,
        qib_threshold=Decimal(str(settings.qib_threshold)),
        retail_threshold=Decimal(str(settings.retail_threshold)),
        overall_threshold=Decimal(str(settings.overall_threshold)),
        gmp_threshold_pct=Decimal(str(settings.gmp_threshold_pct)),
    )


def current_status(ipo: IPO, today: date) -> str:
    if ipo.close_date and ipo.close_date < today:
        return "Expired"
    if ipo.open_date and ipo.open_date > today:
        return "Upcoming"
    if ipo.open_date and ipo.close_date and ipo.open_date <= today <= ipo.close_date:
        return "Open"
    return "Unknown"
