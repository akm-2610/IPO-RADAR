"""Chittorgarh primary IPO scraper."""

from __future__ import annotations

import logging
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from models import IPO
from parsing import clean_text, parse_close_date, parse_open_date
from scrapers.base import BaseScraper, ScrapeError
from scrapers.common import parse_ipo_detail

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://www.chittorgarh.com"
DASHBOARD_URL = f"{BASE_URL}/ipo/ipo_dashboard.asp"


class ChittorgarhScraper(BaseScraper):
    def scrape_active(self, today: date) -> list[IPO]:
        LOGGER.info("Chittorgarh scraper started")
        dashboard = self.get_soup(DASHBOARD_URL)
        links = self._active_detail_links(dashboard, today)
        LOGGER.info("Chittorgarh found %d currently open IPO candidates", len(links))
        records: list[IPO] = []
        for name, url, open_date, close_date in links:
            try:
                detail = self.get_soup(url)
            except ScrapeError:
                LOGGER.warning("Skipping IPO detail page after fetch failure: %s", url)
                continue
            date_fallback = IPO(name=name, open_date=open_date, close_date=close_date)
            record = parse_ipo_detail(
                detail,
                name=name,
                source_url=url,
                today=today,
                fallback=date_fallback,
            )
            if record.open_date and record.close_date and record.open_date <= today <= record.close_date:
                records.append(record)
            else:
                LOGGER.info("%s IPO skipped because it is outside the open date range", name)
        LOGGER.info("Chittorgarh scraper found %d IPOs", len(records))
        return records

    @staticmethod
    def _active_detail_links(
        soup: BeautifulSoup, today: date
    ) -> list[tuple[str, str, date, date]]:
        found: dict[str, tuple[str, str, date, date]] = {}
        for row in soup.select("table tr"):
            for anchor in row.select("a[href]"):
                href = anchor.get("href", "")
                if "/ipo/" not in href or "ipo_dashboard" in href:
                    continue
                label = clean_text(anchor.get_text(" ", strip=True))
                row_text = clean_text(row.get_text(" ", strip=True))
                close_date = parse_close_date(row_text, today)
                open_date = parse_open_date(row_text, today)
                if (
                    open_date is None
                    or close_date is None
                    or open_date > today
                    or close_date < today
                ):
                    continue
                name = clean_text(anchor.get("title") or label)
                # Dashboard link labels often append the date range to the IPO name.
                if close_date:
                    name = name.split(str(close_date.day), 1)[0].strip(" -–")
                url = urljoin(BASE_URL, href)
                found[url] = (name or label, url, open_date, close_date)
        return list(found.values())
