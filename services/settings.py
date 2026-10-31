"""Validated persistent dashboard and alert settings."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


class SettingsError(RuntimeError):
    """Raised when persisted settings cannot be read or safely updated."""


@dataclass(frozen=True)
class RadarSettings:
    gmp_threshold_pct: float = 20.0
    qib_threshold: float = 5.0
    retail_threshold: float = 2.0
    overall_threshold: float = 10.0
    alert_frequency: str = "once_per_ipo"
    refresh_interval_seconds: int = 300


_FREQUENCIES = {"once_per_ipo", "daily", "weekly"}


def load_settings(path: Path) -> RadarSettings:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        settings = RadarSettings()
        save_settings(path, settings)
        return settings
    except (OSError, json.JSONDecodeError) as error:
        raise SettingsError(f"Unable to read settings file {path}.") from error

    try:
        settings = RadarSettings(**raw)
    except (TypeError, ValueError) as error:
        raise SettingsError(f"Settings file {path} has an invalid structure.") from error
    _validate(settings)
    return settings


def save_settings(path: Path, settings: RadarSettings) -> None:
    _validate(settings)
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
            json.dump(asdict(settings), temporary_file, indent=2)
            temporary_file.write("\n")
        os.replace(temporary_path, path)
    except OSError as error:
        raise SettingsError(f"Unable to save settings file {path}.") from error
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _validate(settings: RadarSettings) -> None:
    values = (
        settings.gmp_threshold_pct,
        settings.qib_threshold,
        settings.retail_threshold,
        settings.overall_threshold,
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in values
    ):
        raise SettingsError("Threshold settings must be non-negative numbers.")
    if settings.alert_frequency not in _FREQUENCIES:
        raise SettingsError("Alert frequency must be once_per_ipo, daily, or weekly.")
    if (
        isinstance(settings.refresh_interval_seconds, bool)
        or not isinstance(settings.refresh_interval_seconds, int)
        or not 30 <= settings.refresh_interval_seconds <= 86400
    ):
        raise SettingsError("Refresh interval must be between 30 seconds and 24 hours.")
