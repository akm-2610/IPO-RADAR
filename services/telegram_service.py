"""Telegram integration for dashboard actions."""

from __future__ import annotations

import os

from notifier.telegram import TelegramNotificationError, TelegramNotifier


class TelegramService:
    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = (token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, message: str) -> None:
        if not self.configured:
            raise TelegramNotificationError("Telegram bot credentials are not configured.")
        TelegramNotifier(self.token, self.chat_id).send_message(message)
