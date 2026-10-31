"""Scraper orchestration exposed to the UI and command-line runner."""

from __future__ import annotations

from datetime import date

from main import load_ipo_data
from models import IPO


def fetch_open_ipos(today: date) -> list[IPO]:
    return load_ipo_data(today)
