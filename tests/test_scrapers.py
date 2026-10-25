from datetime import date
from decimal import Decimal

from bs4 import BeautifulSoup

from scrapers.chittorgarh import ChittorgarhScraper
from scrapers.ipo_watch import IpoWatchScraper
from scrapers.common import parse_ipo_detail

TODAY = date(2026, 10, 25)


def test_chittorgarh_extracts_ipo_links_and_closing_date():
    html = """
    <table>
      <tr><th>Company</th><th>Issue Date</th></tr>
      <tr><td><a title="Example IPO" href="/ipo/example-ipo/1/">Example IPO</a></td>
          <td>23 - 27 Oct</td></tr>
    </table>
    """
    result = ChittorgarhScraper._active_detail_links(BeautifulSoup(html, "html.parser"), TODAY)
    assert result == [
        (
            "Example IPO",
            "https://www.chittorgarh.com/ipo/example-ipo/1/",
            date(2026, 10, 23),
            date(2026, 10, 27),
        )
    ]


def test_upcoming_ipo_is_not_classified_as_active():
    html = """
    <table>
      <tr><th>Company</th><th>Issue Date</th></tr>
      <tr><td><a title="Upcoming IPO" href="/ipo/upcoming-ipo/1/">Upcoming IPO</a></td>
          <td>29 Oct to 2 Nov, 2026</td></tr>
    </table>
    """
    assert not ChittorgarhScraper._active_detail_links(
        BeautifulSoup(html, "html.parser"), TODAY
    )


def test_ipo_watch_parses_listing_gmp_and_price_band():
    html = """
    <table>
      <thead>
        <tr><th>Company</th><th>GMP*</th><th>Trend</th><th>Price Band</th><th>Date</th></tr>
      </thead>
      <tbody>
        <tr><td><a href="/example-ipo/">Example IPO</a></td>
            <td>₹25</td><td>Green</td><td>₹90 to ₹100</td><td>24-27 Oct</td></tr>
      </tbody>
    </table>
    """
    records = IpoWatchScraper._parse_listing(BeautifulSoup(html, "html.parser"), TODAY)
    assert len(records) == 1
    assert records[0].name == "Example IPO"
    assert records[0].gmp == Decimal("25")
    assert records[0].issue_price == Decimal("100")
    assert records[0].open_date == date(2026, 10, 24)
    assert records[0].close_date == date(2026, 10, 27)


def test_chittorgarh_reservations_are_not_subscription_metrics():
    html = """
    <h2>IPO Details</h2>
    <table>
      <tr><td>IPO Date</td><td>29 Oct to 2 Nov, 2026</td></tr>
      <tr><td>Price Band</td><td>₹78 to ₹82</td></tr>
    </table>
    <h3>Issue Reservation</h3>
    <table>
      <tr><th>Investor Category</th><th>Shares</th></tr>
      <tr><td>QIB</td><td>Not more than 50% of the Issue</td></tr>
      <tr><td>Retail</td><td>Not more than 35% of the Issue</td></tr>
    </table>
    """
    ipo = parse_ipo_detail(
        BeautifulSoup(html, "html.parser"),
        name="Example IPO",
        today=TODAY,
    )
    assert ipo.name == "Example IPO"
    assert ipo.close_date == date(2026, 11, 2)
    assert ipo.issue_price == Decimal("82")
    assert ipo.qib_subscription is None
    assert ipo.retail_subscription is None


def test_subscription_table_maps_categories_without_marking_qib_as_overall():
    html = """
    <h2>IPO Subscription Status</h2>
    <table>
      <thead><tr><th>Category</th><th>Subscription</th></tr></thead>
      <tbody>
        <tr><td>QIB</td><td>5.5x</td></tr>
        <tr><td>Retail</td><td>2.2x</td></tr>
        <tr><td>Total</td><td>10.5x</td></tr>
      </tbody>
    </table>
    """
    ipo = parse_ipo_detail(BeautifulSoup(html, "html.parser"), name="Example IPO", today=TODAY)
    assert ipo.qib_subscription == Decimal("5.5")
    assert ipo.retail_subscription == Decimal("2.2")
    assert ipo.overall_subscription == Decimal("10.5")
