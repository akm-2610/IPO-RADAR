"""Low-risk health probes with short network timeouts and sanitized errors."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from services.telegram_service import TelegramService

IST = ZoneInfo("Asia/Kolkata")


def check_system_health(
    *,
    telegram: TelegramService,
    scraper_status: str,
    last_scraper_run: str | None,
    last_successful_alert: str | None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    http = session or requests.Session()
    now = datetime.now(IST).isoformat()
    try:
        response = http.get("https://www.chittorgarh.com", timeout=4)
        internet = response.ok
    except requests.RequestException:
        internet = False

    telegram_status = "Not configured"
    if telegram.configured:
        try:
            response = http.get(
                f"https://api.telegram.org/bot{telegram.token}/getMe",
                timeout=4,
            )
            payload = response.json() if response.ok else {}
            telegram_status = (
                "Healthy"
                if isinstance(payload, dict) and payload.get("ok") is True
                else "Failure"
            )
        except (requests.RequestException, ValueError):
            telegram_status = "Failure"

    return {
        "checked_at": now,
        "internet": "Healthy" if internet else "Failure",
        "telegram": telegram_status,
        "scraper": scraper_status,
        "last_scraper_run": last_scraper_run,
        "last_successful_alert": last_successful_alert,
    }
