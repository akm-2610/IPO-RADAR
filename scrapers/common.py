"""HTML-to-IPO mapping shared by both source scrapers."""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from models import IPO
from parsing import (
    clean_text,
    parse_close_date,
    parse_decimal,
    parse_issue_price,
    parse_open_date,
    parse_subscription,
)

_ALIASES = {
    "gmp": ("gmp", "grey market premium", "ipo gmp"),
    "issue_price": ("issue price", "price band", "ipo price band"),
    "qib_subscription": (
        "qib subscription",
        "subscription qib",
        "qualified institutional buyers subscription",
    ),
    "retail_subscription": (
        "retail subscription",
        "rii subscription",
        "subscription retail",
        "retail individual investors subscription",
    ),
    "overall_subscription": ("overall subscription", "total subscription", "subscription"),
    "open_date": ("open date", "ipo open date", "issue open date", "ipo date", "bidding start date"),
    "close_date": ("close date", "closing date", "ipo close date", "issue close date", "bidding end date"),
    "name": ("ipo name", "company name", "name"),
}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def _field(label: str) -> str | None:
    normalized = _key(label)
    for field, aliases in _ALIASES.items():
        normalized_aliases = {_key(alias) for alias in aliases}
        if normalized in normalized_aliases:
            return field
    if "subscription" in normalized:
        if normalized.startswith(("qib", "qualified institutional")):
            return "qib_subscription"
        if normalized.startswith(("retail", "rii")):
            return "retail_subscription"
        if normalized.startswith(("overall", "total")) or normalized == "subscription":
            return "overall_subscription"
    return None


def _subscription_category(label: str) -> str | None:
    normalized = _key(label)
    if normalized.startswith(("qib", "qualified institutional")):
        return "qib_subscription"
    if normalized.startswith(("retail", "rii", "retail individual")):
        return "retail_subscription"
    if normalized.startswith(("overall", "total")):
        return "overall_subscription"
    return None


def _has_subscription_context(table) -> bool:
    caption = table.find("caption")
    previous_heading = table.find_previous(re.compile(r"^h[1-6]$"))
    context = " ".join(
        [
            clean_text(caption.get_text(" ", strip=True)) if caption else "",
            clean_text(previous_heading.get_text(" ", strip=True)) if previous_heading else "",
            " ".join(table.get("class", [])),
            table.get("id", ""),
        ]
    )
    return "subscription" in context.lower() or "bidding" in context.lower()


def _read_table_values(soup: BeautifulSoup) -> dict[str, str]:
    values: dict[str, str] = {}
    for table in soup.select("table"):
        rows = table.select("tr")
        if not rows:
            continue
        header_cells = [clean_text(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
        header_fields = [_field(header) for header in header_cells]
        category_table = (
            bool(header_cells)
            and any(marker in _key(header_cells[0]) for marker in ("category", "investor"))
            and any("subscription" in _key(header) for header in header_cells)
        )
        subscription_context = _has_subscription_context(table) or category_table
        if subscription_context:
            header_fields = [
                None if _key(header) == "subscription" else field
                for header, field in zip(header_cells, header_fields)
            ]
        if any(field for field in header_fields):
            for row in rows[1:]:
                cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
                if len(cells) != len(header_fields):
                    continue
                for field, value in zip(header_fields, cells):
                    if field and value and value not in {"-", "—"}:
                        values.setdefault(field, value)
        if subscription_context and header_cells:
            category_column = 0
            subscription_column = next(
                (
                    index
                    for index, header in enumerate(header_cells)
                    if "subscription" in _key(header) or "times" in _key(header)
                ),
                None,
            )
            for row in rows[1:]:
                cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
                if len(cells) != len(header_cells):
                    continue
                category = _subscription_category(cells[category_column])
                if category and subscription_column is not None:
                    value = cells[subscription_column]
                    if value and value not in {"-", "—"}:
                        values[category] = value
                for index, header in enumerate(header_cells):
                    category = _subscription_category(header)
                    if category and cells[index] and cells[index] not in {"-", "—"}:
                        values[category] = cells[index]
        for row in rows:
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            field = _field(cells[0])
            if field and cells[1]:
                values[field] = cells[1]
                if field == "open_date" and _key(cells[0]) == "ipo date":
                    values["close_date"] = cells[1]
    return values


def _read_text_values(soup: BeautifulSoup) -> dict[str, str]:
    text = clean_text(soup.get_text(" ", strip=True))
    values: dict[str, str] = {}
    patterns = {
        "gmp": r"(?:IPO\s+)?(?:Grey Market Premium|GMP)\s*:?\s*(₹?\s*[-+]?\d[\d,]*(?:\.\d+)?)",
        "issue_price": r"(?:IPO\s+)?(?:Price Band|Issue Price)\s*:?\s*(₹?\s*[\d,]+(?:\.\d+)?(?:\s*(?:-|to)\s*₹?\s*[\d,]+(?:\.\d+)?)?)",
        "qib_subscription": r"\bQIB(?:\s+Subscription)?\s*:?\s*([\d,.]+\s*x?)",
        "retail_subscription": r"\b(?:Retail|RII)(?:\s+Subscription)?\s*:?\s*([\d,.]+\s*x?)",
        "overall_subscription": r"\b(?:Overall|Total)\s+Subscription\s*:?\s*([\d,.]+\s*x?)",
        "open_date": r"(?:IPO\s+)?(?:Open|Opening) Date\s*:?\s*([A-Za-z0-9, /-]{4,30})",
        "close_date": r"(?:IPO\s+)?(?:Close|Closing) Date\s*:?\s*([A-Za-z0-9, /-]{4,30})",
    }
    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            values[field] = clean_text(match.group(1))
    return values


def _value(values: dict[str, str], field: str) -> str | None:
    return values.get(field)


def parse_ipo_detail(
    soup: BeautifulSoup,
    *,
    name: str = "",
    source_url: str | None = None,
    today: date | None = None,
    fallback: IPO | None = None,
) -> IPO:
    values = _read_table_values(soup)
    for field, value in _read_text_values(soup).items():
        values.setdefault(field, value)

    parsed_name = _value(values, "name") or name or (fallback.name if fallback else "")
    gmp = parse_decimal(_value(values, "gmp"))
    issue_price = parse_issue_price(_value(values, "issue_price"))
    qib = parse_subscription(_value(values, "qib_subscription"))
    retail = parse_subscription(_value(values, "retail_subscription"))
    overall = parse_subscription(_value(values, "overall_subscription"))
    open_date = parse_open_date(_value(values, "open_date"), today)
    close_date = parse_close_date(_value(values, "close_date"), today)

    if fallback:
        gmp = gmp if gmp is not None else fallback.gmp
        issue_price = issue_price if issue_price is not None else fallback.issue_price
        qib = qib if qib is not None else fallback.qib_subscription
        retail = retail if retail is not None else fallback.retail_subscription
        overall = overall if overall is not None else fallback.overall_subscription
        open_date = open_date or fallback.open_date
        close_date = close_date or fallback.close_date

    return IPO(
        name=parsed_name,
        gmp=gmp,
        issue_price=issue_price,
        qib_subscription=qib,
        retail_subscription=retail,
        overall_subscription=overall,
        open_date=open_date,
        close_date=close_date,
        source_url=source_url,
    )
