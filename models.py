"""Shared IPO data model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class IPO:
    name: str
    gmp: Decimal | None = None
    issue_price: Decimal | None = None
    qib_subscription: Decimal | None = None
    retail_subscription: Decimal | None = None
    overall_subscription: Decimal | None = None
    open_date: date | None = None
    close_date: date | None = None
    source_url: str | None = None

    @property
    def gmp_percent(self) -> Decimal | None:
        if self.gmp is None or self.issue_price is None or self.issue_price <= 0:
            return None
        return self.gmp / self.issue_price * Decimal("100")
