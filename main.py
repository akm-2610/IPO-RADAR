"""Daily IPO-RADAR entry point."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from alert_history import AlertHistoryError, JSONAlertHistory
from filters.alerts import alert_rejection_reasons
from notifier.telegram import TelegramNotificationError, TelegramNotifier
from scrapers.chittorgarh import ChittorgarhScraper
from scrapers.ipo_watch import IpoWatchScraper
from scrapers.base import ScrapeError
from models import IPO

IST = ZoneInfo("Asia/Kolkata")
LOGGER = logging.getLogger("ipo_radar")
PROJECT_ROOT = Path(__file__).resolve().parent
ALERT_HISTORY_PATH = PROJECT_ROOT / "alerts_sent.json"
TEST_MESSAGE = "✅ IPO-RADAR TEST MESSAGE\n\nTelegram integration is working."


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    root_logger = logging.getLogger()
    if not any(getattr(handler, "_ipo_radar_file_handler", False) for handler in root_logger.handlers):
        log_directory = PROJECT_ROOT / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_directory / "ipo_radar.log",
            mode="a",
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        file_handler._ipo_radar_file_handler = True
        root_logger.addHandler(file_handler)


def load_ipo_data(today: date) -> list[IPO]:
    """Return primary data, using IPO Watch only when Chittorgarh has no data."""
    primary = ChittorgarhScraper()
    try:
        records = primary.scrape_active(today)
    except ScrapeError as error:
        LOGGER.warning("Chittorgarh unavailable; trying IPO Watch: %s", error)
        records = []

    if records:
        return records

    LOGGER.info("Chittorgarh returned no active IPOs; trying IPO Watch.")
    return IpoWatchScraper().scrape_active(today)


def format_alert(ipo: IPO) -> str:
    return (
        f"🚨 IPO ALERT\n\n"
        f"IPO: {ipo.name}\n"
        f"QIB: {ipo.qib_subscription}x\n"
        f"Retail: {ipo.retail_subscription}x\n"
        f"Overall: {ipo.overall_subscription}x\n"
        f"GMP: {ipo.gmp_percent:.2f}%\n\n"
        f"Open Date: {ipo.open_date.isoformat()}\n"
        f"Close Date: {ipo.close_date.isoformat()}"
    )


def run() -> int:
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
    configure_logging()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        LOGGER.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be configured.")
        return 1

    if os.getenv("TEST_MODE", "").strip().lower() == "true":
        try:
            TelegramNotifier(token, chat_id).send_message(TEST_MESSAGE)
        except TelegramNotificationError as error:
            LOGGER.error("Unable to send Telegram test message: %s", error)
            return 1
        LOGGER.info("Telegram test message sent.")
        return 0

    today = datetime.now(IST).date()
    try:
        records = load_ipo_data(today)
    except ScrapeError as error:
        LOGGER.error("Both IPO data sources failed: %s", error)
        return 1

    try:
        history = JSONAlertHistory(ALERT_HISTORY_PATH)
    except AlertHistoryError as error:
        LOGGER.error("Unable to load duplicate-alert history: %s", error)
        return 1

    matches: list[IPO] = []
    seen: set[str] = set()
    for ipo in records:
        rejection_reasons = alert_rejection_reasons(ipo, today)
        if rejection_reasons:
            LOGGER.info("%s IPO rejected because %s", ipo.name, ", ".join(rejection_reasons))
            continue
        LOGGER.info("%s IPO meets all alert conditions", ipo.name)
        key = history.key_for(ipo)
        if history.has_alerted(ipo) or key in seen:
            LOGGER.info("%s IPO alert skipped because it was already sent", ipo.name)
            continue
        matches.append(ipo)
        seen.add(key)
    if not matches:
        LOGGER.info("No unsent IPOs met all alert conditions.")
        return 0

    notifier = TelegramNotifier(token, chat_id)
    try:
        for ipo in matches:
            notifier.send_message(format_alert(ipo))
            history.record_alert(ipo, today)
            LOGGER.info("%s IPO alert sent", ipo.name)
    except (TelegramNotificationError, AlertHistoryError) as error:
        LOGGER.error("Unable to deliver or record IPO alert: %s", error)
        return 1

    LOGGER.info("Sent %d IPO alert(s).", len(matches))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())