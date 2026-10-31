"""Persistent dashboard snapshots and delivery events."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections import deque
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from models import IPO

LOGGER = logging.getLogger("ipo_radar.state")
IST = ZoneInfo("Asia/Kolkata")


class StateStoreError(RuntimeError):
    """Raised when dashboard state cannot be persisted."""


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def ipo_to_dict(ipo: IPO) -> dict[str, Any]:
    return {
        "name": ipo.name,
        "gmp": ipo.gmp,
        "issue_price": ipo.issue_price,
        "qib_subscription": ipo.qib_subscription,
        "retail_subscription": ipo.retail_subscription,
        "overall_subscription": ipo.overall_subscription,
        "open_date": ipo.open_date,
        "close_date": ipo.close_date,
        "source_url": ipo.source_url,
        "issue_size": ipo.issue_size,
        "price_band": ipo.price_band,
        "sector": ipo.sector,
    }


def ipo_from_dict(raw: dict[str, Any]) -> IPO:
    def decimal_value(field: str) -> Decimal | None:
        value = raw.get(field)
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError(f"Invalid decimal value for {field}.") from error

    def date_value(field: str) -> date | None:
        value = raw.get(field)
        return date.fromisoformat(value) if value else None

    return IPO(
        name=str(raw["name"]),
        gmp=decimal_value("gmp"),
        issue_price=decimal_value("issue_price"),
        qib_subscription=decimal_value("qib_subscription"),
        retail_subscription=decimal_value("retail_subscription"),
        overall_subscription=decimal_value("overall_subscription"),
        open_date=date_value("open_date"),
        close_date=date_value("close_date"),
        source_url=raw.get("source_url"),
        issue_size=raw.get("issue_size"),
        price_band=raw.get("price_band"),
        sector=raw.get("sector"),
    )


class DashboardState:
    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory
        self.snapshot_path = data_directory / "ipo_snapshots.jsonl"
        self.events_path = data_directory / "alert_events.jsonl"
        self.health_path = data_directory / "system_health.json"

    def record_snapshot(
        self, records: list[IPO], *, source: str, captured_at: datetime | None = None
    ) -> None:
        timestamp = captured_at or datetime.now(IST)
        self._append(
            self.snapshot_path,
            {"timestamp": timestamp, "source": source, "ipos": [ipo_to_dict(row) for row in records]},
        )

    def read_snapshots(self, *, limit: int = 500) -> list[dict[str, Any]]:
        return self._read_jsonl(self.snapshot_path, limit=limit)

    def record_alert(
        self,
        *,
        ipo: IPO,
        message: str,
        status: str,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        event = {
            "timestamp": timestamp or datetime.now(IST),
            "ipo_name": ipo.name,
            "gmp": ipo.gmp,
            "gmp_percent": ipo.gmp_percent,
            "message": message,
            "status": status,
        }
        self._append(self.events_path, event)
        return event

    def read_alerts(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        return self._read_jsonl(self.events_path, limit=limit)

    def clear_alerts(self) -> None:
        self._atomic_write(self.events_path, "")

    def write_health(self, values: dict[str, Any]) -> None:
        self._atomic_write(
            self.health_path,
            json.dumps(values, default=_json_value, indent=2) + "\n",
        )

    def read_health(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.health_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            raise StateStoreError(f"Unable to read dashboard health at {self.health_path}.") from error
        if not isinstance(raw, dict):
            raise StateStoreError("Dashboard health file has an invalid format.")
        return raw

    def _append(self, path: Path, event: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as output:
                output.write(json.dumps(event, default=_json_value, separators=(",", ":")) + "\n")
        except OSError as error:
            raise StateStoreError(f"Unable to append dashboard state to {path}.") from error
        if path == self.snapshot_path:
            self._retain_recent(path, 500)
        elif path == self.events_path:
            self._retain_recent(path, 1000)

    def _retain_recent(self, path: Path, limit: int) -> None:
        try:
            with path.open("r", encoding="utf-8") as source:
                lines = deque(source, maxlen=limit + 1)
            if len(lines) > limit:
                self._atomic_write(path, "".join(list(lines)[-limit:]))
        except OSError as error:
            raise StateStoreError(f"Unable to compact dashboard state at {path}.") from error

    def _read_jsonl(self, path: Path, *, limit: int) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        try:
            with path.open("r", encoding="utf-8") as source:
                lines = list(deque(source, maxlen=limit))
        except FileNotFoundError:
            return []
        except OSError as error:
            raise StateStoreError(f"Unable to read dashboard state at {path}.") from error
        events = []
        for line_number, line in enumerate(lines, start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                LOGGER.warning("Skipping malformed JSONL record in %s near line %d", path.name, line_number)
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def _atomic_write(self, path: Path, content: str) -> None:
        temporary_path: str | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                temporary_file.write(content)
            os.replace(temporary_path, path)
        except OSError as error:
            raise StateStoreError(f"Unable to update dashboard state at {path}.") from error
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
