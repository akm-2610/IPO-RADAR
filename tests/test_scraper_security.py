import pytest

from scrapers.base import BaseScraper, ScrapeError


class FakeResponse:
    def __init__(self, *, status_code=200, text="<p>ok</p>", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.closed = False

    @property
    def is_redirect(self):
        return self.status_code in {301, 302, 303, 307, 308}

    @property
    def is_permanent_redirect(self):
        return self.status_code in {301, 308}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.urls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.urls.append((url, kwargs))
        return next(self.responses)


class ExampleScraper(BaseScraper):
    allowed_hosts = frozenset({"example.com", "www.example.com"})


def test_scraper_rejects_non_allowlisted_urls_before_request():
    session = FakeSession([])
    scraper = ExampleScraper(session)

    with pytest.raises(ScrapeError, match="non-allowlisted"):
        scraper.get_soup("https://attacker.example/data")

    assert session.urls == []


def test_scraper_rejects_http_even_for_allowed_host():
    session = FakeSession([])
    scraper = ExampleScraper(session)

    with pytest.raises(ScrapeError, match="non-allowlisted"):
        scraper.get_soup("http://example.com/data")

    assert session.urls == []


def test_scraper_validates_redirect_targets():
    redirect = FakeResponse(status_code=302, headers={"Location": "https://attacker.example/"})
    session = FakeSession([redirect])
    scraper = ExampleScraper(session)

    with pytest.raises(ScrapeError, match="non-allowlisted"):
        scraper.get_soup("https://example.com/data")

    assert redirect.closed
    assert len(session.urls) == 1
    assert session.urls[0][1]["allow_redirects"] is False


def test_scraper_disables_automatic_redirects_and_accepts_allowed_https():
    response = FakeResponse()
    session = FakeSession([response])
    scraper = ExampleScraper(session)

    soup = scraper.get_soup("https://example.com/data")

    assert soup.p.get_text() == "ok"
    assert response.closed
    assert session.urls[0][1]["allow_redirects"] is False
