"""Replaceable, transparent baseline scoring; not an investment recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from models import IPO


@dataclass(frozen=True)
class ScoreResult:
    score: int | None
    label: str
    explanation: str


class IPOScorer(Protocol):
    def score(self, ipo: IPO) -> ScoreResult: ...


class BaselineIPOScorer:
    """Simple weighted signal that can be replaced by a trained model later."""

    def score(self, ipo: IPO) -> ScoreResult:
        signals = (
            ipo.gmp_percent,
            ipo.qib_subscription,
            ipo.retail_subscription,
            ipo.overall_subscription,
        )
        if any(value is None for value in signals):
            return ScoreResult(None, "Not rated", "Required GMP/subscription data is incomplete.")

        assert ipo.gmp_percent is not None
        assert ipo.qib_subscription is not None
        assert ipo.retail_subscription is not None
        assert ipo.overall_subscription is not None
        gmp_score = min(ipo.gmp_percent / Decimal("50"), Decimal("1")) * Decimal("40")
        qib_score = min(ipo.qib_subscription / Decimal("10"), Decimal("1")) * Decimal("15")
        retail_score = min(ipo.retail_subscription / Decimal("5"), Decimal("1")) * Decimal("15")
        overall_score = min(ipo.overall_subscription / Decimal("50"), Decimal("1")) * Decimal("30")
        score = int((gmp_score + qib_score + retail_score + overall_score).quantize(Decimal("1")))
        label = "Strong Buy" if score >= 75 else "Watchlist" if score >= 45 else "Avoid"
        return ScoreResult(score, label, "Signals use GMP and subscription data only; historical listing gains and sector demand are not yet available.")
