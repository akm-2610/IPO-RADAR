"""Parsing helpers shared by the IPO source scrapers."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from dateutil import parser as date_parser


_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
_DATE_TOKEN = re.compile(
    r"\b\d{1,2}\s*(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)(?:\s*,?\s*\d{4})?\b",
    re.IGNORECASE,
)
_MONTH_FIRST_DATE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
    re.IGNORECASE,
)
_COMPACT_DATE_RANGE = re.compile(
    r"\b(?P<start>\d{1,2})\s*[-–]\s*(?P<end>\d{1,2})\s*"
    r"(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)(?:\s*,?\s*(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def parse_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    match = _NUMBER.search(value.replace("−", "-"))
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def parse_subscription(value: str | None) -> Decimal | None:
    if not value or value.strip() in {"-", "—", "N/A"}:
        return None
    parsed = parse_decimal(value)
    if parsed is None:
        return None
    if "%" in value and "x" not in value.lower():
        return parsed / Decimal("100")
    return parsed


def parse_issue_price(value: str | None) -> Decimal | None:
    """Use the upper end of a price band to avoid overstating GMP percentage."""
    if not value:
        return None
    prices = [parse_decimal(piece) for piece in re.split(r"\s*(?:-|–|—|to)\s*", value, flags=re.I)]
    valid = [price for price in prices if price is not None]
    return max(valid) if valid else None


def _infer_year(parsed: date, reference: date) -> date:
    candidates = []
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            candidates.append(parsed.replace(year=year))
        except ValueError:
            continue
    return min(candidates, key=lambda candidate: abs((candidate - reference).days))


def parse_close_date(value: str | None, today: date | None = None) -> date | None:
    if not value:
        return None
    reference = today or date.today()
    text = clean_text(value)

    iso = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    tokens = list(_DATE_TOKEN.finditer(text))
    if tokens:
        token = tokens[-1].group(0)
    elif _MONTH_FIRST_DATE.search(text):
        token = _MONTH_FIRST_DATE.search(text).group(0)
    else:
        numeric = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})\b", text)
        if not numeric:
            return None
        token = numeric[-1]
    explicit_year = re.search(r"\b20\d{2}\b", text)
    if explicit_year and not re.search(r"\b20\d{2}\b", token):
        token = f"{token}, {explicit_year.group(0)}"

    try:
        parsed = date_parser.parse(
            token,
            default=datetime(reference.year, 1, 1),
            dayfirst=True,
            fuzzy=False,
        ).date()
    except (ValueError, OverflowError):
        return None

    if not re.search(r"\b\d{4}\b", token):
        parsed = _infer_year(parsed, reference)
    return parsed


def parse_open_date(value: str | None, today: date | None = None) -> date | None:
    if not value:
        return None
    reference = today or date.today()
    text = clean_text(value)
    compact_range = _COMPACT_DATE_RANGE.search(text)
    tokens = list(_DATE_TOKEN.finditer(text))

    if compact_range and len(tokens) == 1:
        close_date = parse_close_date(text, reference)
        if close_date is None:
            return None
        start_day = int(compact_range.group("start"))
        end_day = int(compact_range.group("end"))
        start_month = close_date.month
        start_year = close_date.year
        if start_day > end_day:
            start_month -= 1
            if start_month == 0:
                start_month = 12
                start_year -= 1
        try:
            return date(start_year, start_month, start_day)
        except ValueError:
            return None

    if tokens:
        token = tokens[0].group(0)
    elif _MONTH_FIRST_DATE.search(text):
        token = _MONTH_FIRST_DATE.search(text).group(0)
    else:
        return parse_close_date(text, reference)

    explicit_year = re.search(r"\b20\d{2}\b", text)
    if explicit_year and not re.search(r"\b20\d{2}\b", token):
        token = f"{token}, {explicit_year.group(0)}"
    try:
        parsed = date_parser.parse(
            token,
            default=datetime(reference.year, 1, 1),
            dayfirst=True,
            fuzzy=False,
        ).date()
    except (ValueError, OverflowError):
        return None
    if not re.search(r"\b\d{4}\b", token):
        parsed = _infer_year(parsed, reference)
    return parsed
