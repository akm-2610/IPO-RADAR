"""Low-risk health probes with short network timeouts and sanitized errors."""

from __future__ import annotations

import os
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

    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    github_status = "Not configured"
    if repository and "/" in repository:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = http.get(
                f"https://api.github.com/repos/{repository}/actions/runs?per_page=1",
                headers=headers,
                timeout=5,
            )
            if response.ok:
                payload = response.json()
                runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
                if runs:
                    conclusion = runs[0].get("conclusion")
                    github_status = "Healthy" if conclusion in {"success", None} else "Warning"
                else:
                    github_status = "No runs"
            else:
                github_status = "Unavailable"
        except (requests.RequestException, ValueError):
            github_status = "Unavailable"

    return {
        "checked_at": now,
        "internet": "Healthy" if internet else "Failure",
        "telegram": telegram_status,
        "scraper": scraper_status,
        "last_scraper_run": last_scraper_run,
        "last_successful_alert": last_successful_alert,
        "github_actions": github_status,
    }
