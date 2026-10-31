"""Formatting helpers for the IPO dashboard."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from models import IPO
from services.ipo_service import current_status, rejection_reasons
from services.settings import RadarSettings
from services.state_store import ipo_from_dict


def _format_demand(value: Decimal | None) -> str:
    return f"{value.normalize():f}x" if value is not None else "N/A"


def build_ipo_table(
    records: list[IPO],
    *,
    today: date | None = None,
    settings: RadarSettings | None = None,
    last_alerted: set[str] | None = None,
) -> pd.DataFrame:
    today = today or date.today()
    settings = settings or RadarSettings()
    last_alerted = last_alerted or set()
    rows = [
        {
            "IPO": ipo.name,
            "IPO Name": ipo.name,
            "Open Date": ipo.open_date.isoformat() if ipo.open_date else "N/A",
            "Close Date": ipo.close_date.isoformat() if ipo.close_date else "N/A",
            "Issue Size": ipo.issue_size or "N/A",
            "Price Band": ipo.price_band or (f"₹{ipo.issue_price}" if ipo.issue_price is not None else "N/A"),
            "Sector": ipo.sector or "N/A",
            "GMP": f"₹{ipo.gmp}" if ipo.gmp is not None else "N/A",
            "GMP %": float(ipo.gmp_percent) if ipo.gmp_percent is not None else None,
            "QIB Demand": _format_demand(ipo.qib_subscription),
            "Retail Demand": _format_demand(ipo.retail_subscription),
            "Overall Demand": _format_demand(ipo.overall_subscription),
            "Subscription Status": _subscription_status(ipo),
            "Eligibility Status": "Eligible" if not rejection_reasons(ipo, today, settings) else "Not eligible",
            "Eligibility Reasons": ", ".join(rejection_reasons(ipo, today, settings)) or "All rules passed",
            "Telegram Alert Status": "Sent" if ipo.name.casefold() in last_alerted else "Not sent",
            "Days Remaining": (ipo.close_date - today).days if ipo.close_date else None,
            "Status": current_status(ipo, today),
            "Source": _source_name(ipo.source_url),
        }
        for ipo in records
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "IPO",
            "IPO Name",
            "Open Date",
            "Close Date",
            "Issue Size",
            "Price Band",
            "Sector",
            "GMP",
            "GMP %",
            "QIB Demand",
            "Retail Demand",
            "Overall Demand",
            "Subscription Status",
            "Eligibility Status",
            "Eligibility Reasons",
            "Telegram Alert Status",
            "Days Remaining",
            "Status",
            "Source",
        ],
    )


def _subscription_status(ipo: IPO) -> str:
    values = (ipo.qib_subscription, ipo.retail_subscription, ipo.overall_subscription)
    if all(value is None for value in values):
        return "Unavailable"
    if any(value is None for value in values):
        return "Partial"
    return "Live"


def _source_name(url: str | None) -> str:
    if not url:
        return "Unknown"
    if "chittorgarh" in url:
        return "Chittorgarh"
    if "ipowatch" in url:
        return "IPO Watch"
    return "Other"


def snapshots_to_frame(snapshots: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for snapshot in snapshots:
        timestamp = snapshot.get("timestamp")
        try:
            captured = datetime.fromisoformat(timestamp)
        except (TypeError, ValueError):
            continue
        for raw_ipo in snapshot.get("ipos", []):
            try:
                ipo = ipo_from_dict(raw_ipo)
            except (KeyError, TypeError, ValueError):
                continue
            rows.append(
                {
                    "Timestamp": captured,
                    "IPO Name": ipo.name,
                    "GMP %": float(ipo.gmp_percent) if ipo.gmp_percent is not None else None,
                    "GMP ₹": float(ipo.gmp) if ipo.gmp is not None else None,
                    "Sector": ipo.sector,
                }
            )
    return pd.DataFrame(rows, columns=["Timestamp", "IPO Name", "GMP %", "GMP ₹", "Sector"])
