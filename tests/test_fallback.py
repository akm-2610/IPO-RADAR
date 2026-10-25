from datetime import date

import main
from scrapers.base import ScrapeError


class FakeScraper:
    def __init__(self, result=None, error=None):
        self.result = result or []
        self.error = error
        self.calls = 0

    def scrape_active(self, today):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_ipo_watch_is_used_if_primary_is_empty(monkeypatch):
    fallback_records = [object()]
    fallback = FakeScraper(fallback_records)
    monkeypatch.setattr(main, "ChittorgarhScraper", lambda: FakeScraper())
    monkeypatch.setattr(main, "IpoWatchScraper", lambda: fallback)

    assert main.load_ipo_data(date(2026, 10, 25)) is fallback_records
    assert fallback.calls == 1


def test_primary_records_are_not_merged_with_fallback(monkeypatch):
    primary_records = [object()]
    fallback = FakeScraper([object()])
    monkeypatch.setattr(main, "ChittorgarhScraper", lambda: FakeScraper(primary_records))
    monkeypatch.setattr(main, "IpoWatchScraper", lambda: fallback)

    assert main.load_ipo_data(date(2026, 10, 25)) is primary_records
    assert fallback.calls == 0


def test_ipo_watch_is_used_if_primary_fails(monkeypatch):
    fallback_records = [object()]
    monkeypatch.setattr(
        main,
        "ChittorgarhScraper",
        lambda: FakeScraper(error=ScrapeError("primary unavailable")),
    )
    fallback = FakeScraper(fallback_records)
    monkeypatch.setattr(main, "IpoWatchScraper", lambda: fallback)

    assert main.load_ipo_data(date(2026, 10, 25)) is fallback_records
    assert fallback.calls == 1
