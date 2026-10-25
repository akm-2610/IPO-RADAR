"""Shared HTTP and HTML helpers for source scrapers."""

from __future__ import annotations

import logging

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)


class ScrapeError(RuntimeError):
    """Raised when an IPO source cannot be read or parsed."""


class BaseScraper:
    timeout = (5, 20)

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; IPO-RADAR/1.0; "
                    "+https://github.com/)"
                )
            }
        )

    def get_soup(self, url: str) -> BeautifulSoup:
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as error:
            LOGGER.warning("Request to %s failed: %s", url, error)
            raise ScrapeError(f"Unable to retrieve IPO data from {url}") from error
        return BeautifulSoup(response.text, "html.parser")
