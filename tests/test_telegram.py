import pytest

from notifier.telegram import TelegramNotificationError, TelegramNotifier


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.request = None

    def post(self, url, *, json, timeout):
        self.request = (url, json, timeout)
        return self.response


def test_telegram_notifier_posts_plain_text():
    session = FakeSession(FakeResponse({"ok": True}))
    TelegramNotifier("secret-token", "123", session=session).send_message("alert")
    assert session.request[1] == {"chat_id": "123", "text": "alert"}
    assert session.request[2] == 15


def test_telegram_notifier_reports_api_rejection():
    notifier = TelegramNotifier(
        "secret-token", "123", session=FakeSession(FakeResponse({"ok": False}))
    )
    with pytest.raises(TelegramNotificationError, match="rejected"):
        notifier.send_message("alert")
