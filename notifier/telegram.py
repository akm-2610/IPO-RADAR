"""Telegram Bot API notifier."""

from __future__ import annotations

import requests


class TelegramNotificationError(RuntimeError):
    """Raised when Telegram rejects or cannot receive a message."""


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        session: requests.Session | None = None,
        timeout: float = 15,
    ) -> None:
        if not bot_token.strip() or not chat_id.strip():
            raise ValueError("A Telegram bot token and chat ID are required.")
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._session = session or requests.Session()
        self._timeout = timeout

    def send_message(self, text: str) -> None:
        try:
            response = self._session.post(
                self._url,
                json={"chat_id": self._chat_id, "text": text},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            # Do not expose the token-bearing Bot API URL in exception messages.
            raise TelegramNotificationError(
                "Telegram request failed due to a network or HTTP error."
            ) from None
        except ValueError:
            raise TelegramNotificationError("Telegram returned an invalid response.") from None

        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise TelegramNotificationError("Telegram rejected the alert message.")
