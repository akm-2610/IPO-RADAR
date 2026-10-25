"""Persistent JSON tracking for IPOs that have already generated alerts."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path

from models import IPO


class AlertHistoryError(RuntimeError):
    """Raised when alert history cannot be read or safely updated."""


class JSONAlertHistory:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._sent: dict[str, str] = {}
        except OSError as error:
            raise AlertHistoryError(f"Unable to read alert history at {path}.") from error
        else:
            try:
                data = json.loads(content)
            except json.JSONDecodeError as error:
                raise AlertHistoryError(f"Alert history at {path} is not valid JSON.") from error
            if not isinstance(data, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in data.items()
            ):
                raise AlertHistoryError(f"Alert history at {path} has an invalid format.")
            self._sent = data

    @staticmethod
    def key_for(ipo: IPO) -> str:
        normalized_name = re.sub(r"[^a-z0-9]+", "-", ipo.name.casefold()).strip("-")
        if not normalized_name or ipo.open_date is None:
            raise ValueError("An IPO name and open date are required for alert tracking.")
        return f"{normalized_name}:{ipo.open_date.isoformat()}"

    def has_alerted(self, ipo: IPO) -> bool:
        return self.key_for(ipo) in self._sent

    def record_alert(self, ipo: IPO, sent_on: date) -> None:
        self._sent[self.key_for(ipo)] = sent_on.isoformat()
        self._write()

    def _write(self) -> None:
        temporary_path: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                json.dump(self._sent, temporary_file, indent=2, sort_keys=True)
                temporary_file.write("\n")
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise AlertHistoryError(f"Unable to write alert history at {self.path}.") from error
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
