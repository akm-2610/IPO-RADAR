"""IPO Watch fallback scraper."""

from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from models import IPO
from parsing import (
    clean_text,
    parse_close_date,
    parse_decimal,
    parse_issue_price,
    parse_open_date,
)
from scrapers.base import BaseScraper, ScrapeError
from scrapers.common import parse_ipo_detail

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://ipowatch.in"
LIST_URL = f"{BASE_URL}/ipo-grey-market-premium/"


class IpoWatchScraper(BaseScraper):
    def scrape_active(self, today: date) -> list[IPO]:
        LOGGER.info("IPO Watch scraper started")
        soup = self.get_soup(LIST_URL)
        summaries = self._parse_listing(soup, today)
        records: list[IPO] = []
        for summary in summaries:
            if summary.source_url:
                try:
                    detail = self.get_soup(summary.source_url)
                except ScrapeError as error:
                    LOGGER.warning("IPO Watch detail unavailable for %s: %s", summary.name, error)
                else:
                    summary = parse_ipo_detail(
                        detail,
                        name=summary.name,
                        source_url=summary.source_url,
                        today=today,
                        fallback=summary,
                    )
            records.append(summary)
        LOGGER.info("IPO Watch scraper found %d currently open IPOs", len(records))
        return records

    @staticmethod
    def _parse_listing(soup: BeautifulSoup, today: date) -> list[IPO]:
        records: dict[str, IPO] = {}
        for table in soup.select("table"):
            header_row = table.select_one("thead tr")
            if header_row is None:
                header_row = next(
                    (
                        row
                        for row in table.select("tr")
                        if row.find_all("th") and not row.find_all("td")
                    ),
                    None,
                )
            if header_row is None:
                continue
            headers = [
                re.sub(r"[^a-z0-9]+", "", clean_text(cell.get_text(" ", strip=True)).lower())
                for cell in header_row.find_all(["th", "td"])
            ]
            if not headers or "company" not in headers[0]:
                continue
            columns = {header: index for index, header in enumerate(headers)}
            for row in table.select("tr"):
                if row is header_row:
                    continue
                cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
                if len(cells) < len(headers):
                    continue
                anchor = row.select_one("a[href]")
                name = clean_text(anchor.get_text(" ", strip=True)) if anchor else cells[0]
                if not name:
                    continue
                date_text = cells[columns["date"]] if "date" in columns else ""
                close_date = parse_close_date(date_text, today)
                open_date = parse_open_date(date_text, today)
                if (
                    open_date is None
                    or close_date is None
                    or open_date > today
                    or close_date < today
                ):
                    continue
                gmp_text = cells[columns["gmp"]] if "gmp" in columns else ""
                price_text = cells[columns["priceband"]] if "priceband" in columns else ""
                url = urljoin(BASE_URL, anchor.get("href", "")) if anchor else None
                records[name.casefold()] = IPO(
                    name=name,
                    gmp=parse_decimal(gmp_text),
                    issue_price=parse_issue_price(price_text),
                    open_date=open_date,
                    close_date=close_date,
                    source_url=url,
                )
        return list(records.values())
