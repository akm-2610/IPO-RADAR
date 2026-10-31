"""Shared HTTP and HTML helpers for source scrapers."""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)


class ScrapeError(RuntimeError):
    """Raised when an IPO source cannot be read or parsed."""


class BaseScraper:
    timeout = (5, 20)
    allowed_hosts: frozenset[str] = frozenset()
    max_redirects = 3

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
        current_url = url
        for redirect_count in range(self.max_redirects + 1):
            try:
                parsed_url = urlsplit(current_url)
                port = parsed_url.port
            except ValueError:
                raise ScrapeError("Blocked a malformed scraper URL.") from None
            host = (parsed_url.hostname or "").lower()
            if (
                parsed_url.scheme != "https"
                or host not in self.allowed_hosts
                or port not in (None, 443)
                or parsed_url.username is not None
                or parsed_url.password is not None
            ):
                raise ScrapeError("Blocked a scraper request to a non-allowlisted URL.")

            try:
                response = self.session.get(
                    current_url,
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                LOGGER.warning("Request to %s failed: %s", host, type(error).__name__)
                raise ScrapeError(f"Unable to retrieve IPO data from {host}") from None

            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                response.close()
                if not location or redirect_count >= self.max_redirects:
                    raise ScrapeError("Scraper request exceeded its redirect limit.")
                current_url = urljoin(current_url, location)
                continue

            try:
                response.raise_for_status()
                content = response.text
            except requests.RequestException as error:
                LOGGER.warning("Request to %s failed: %s", host, type(error).__name__)
                raise ScrapeError(f"Unable to retrieve IPO data from {host}") from None
            finally:
                response.close()
            return BeautifulSoup(content, "html.parser")

        raise ScrapeError("Scraper request exceeded its redirect limit.")
