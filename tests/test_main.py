from datetime import date, datetime
from decimal import Decimal

import main
import pytest
from models import IPO


@pytest.fixture(autouse=True)
def remove_ipo_file_handler_after_test():
    yield
    root_logger = main.logging.getLogger()
    for handler in list(root_logger.handlers):
        if getattr(handler, "_ipo_radar_file_handler", False):
            root_logger.removeHandler(handler)
            handler.close()


class FixedDateTime:
    @staticmethod
    def now(timezone):
        return datetime(2026, 10, 25, 16, 0, tzinfo=timezone)


class RecordingNotifier:
    messages = []

    def __init__(self, token, chat_id):
        pass

    def send_message(self, message):
        self.messages.append(message)


def test_run_sends_each_qualifying_ipo_only_once(monkeypatch, tmp_path):
    ipo = IPO(
        name="Example IPO",
        gmp=Decimal("25"),
        issue_price=Decimal("100"),
        qib_subscription=Decimal("5.5"),
        retail_subscription=Decimal("2.5"),
        overall_subscription=Decimal("12"),
        open_date=date(2026, 10, 20),
        close_date=date(2026, 10, 30),
    )
    monkeypatch.setattr(main, "datetime", FixedDateTime)
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "load_ipo_data", lambda today: [ipo])
    monkeypatch.setattr(main, "ALERT_HISTORY_PATH", tmp_path / "alerts_sent.json")
    monkeypatch.setattr(main, "TelegramNotifier", RecordingNotifier)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setenv("TEST_MODE", "false")
    RecordingNotifier.messages.clear()

    assert main.run() == 0
    assert main.run() == 0
    assert len(RecordingNotifier.messages) == 1


def test_run_loads_dotenv_before_reading_environment(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        main,
        "load_dotenv",
        lambda *, dotenv_path: events.append(("dotenv", dotenv_path)),
    )
    original_getenv = main.os.getenv

    def tracked_getenv(name, default=None):
        events.append(("getenv", name))
        if name == "LOG_LEVEL":
            return "INFO"
        if name == "TELEGRAM_BOT_TOKEN":
            return ""
        if name == "TELEGRAM_CHAT_ID":
            return ""
        if name == "TEST_MODE":
            return "false"
        return original_getenv(name, default)

    monkeypatch.setattr(main.os, "getenv", tracked_getenv)
    monkeypatch.setattr(main, "ALERT_HISTORY_PATH", tmp_path / "alerts_sent.json")

    assert main.run() == 1
    assert events[0] == ("dotenv", main.PROJECT_ROOT / ".env")
    assert events[1] == ("getenv", "LOG_LEVEL")


def test_test_mode_sends_message_without_scraping_or_filtering(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setenv("TEST_MODE", "true")

    def fail_if_scraped(today):
        raise AssertionError("Scraping should not run in TEST_MODE.")

    def fail_if_filtered(ipo, today):
        raise AssertionError("IPO filtering should not run in TEST_MODE.")

    monkeypatch.setattr(main, "load_ipo_data", fail_if_scraped)
    monkeypatch.setattr(main, "alert_rejection_reasons", fail_if_filtered)
    monkeypatch.setattr(main, "TelegramNotifier", RecordingNotifier)
    RecordingNotifier.messages.clear()

    assert main.run() == 0
    assert RecordingNotifier.messages == [main.TEST_MESSAGE]
    assert main.TEST_MESSAGE == (
        "✅ IPO-RADAR TEST MESSAGE\n\nTelegram integration is working."
    )
