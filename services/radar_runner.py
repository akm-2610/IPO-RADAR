"""Run the radar from the dashboard and preserve a user-facing outcome."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

LOGGER = logging.getLogger("ipo_radar.dashboard.runner")


@dataclass(frozen=True)
class RadarRunFeedback:
    level: str
    message: str
    details: tuple[str, ...]


class _RunLogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.messages: list[tuple[int, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append((record.levelno, self.format(record)))


def run_radar_with_feedback(runner: Callable[[], int]) -> RadarRunFeedback:
    """Capture radar logs so button outcomes survive Streamlit reruns."""
    root_logger = logging.getLogger()
    capture = _RunLogCapture()
    capture.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root_logger.addHandler(capture)

    try:
        exit_code = runner()
    except Exception:
        LOGGER.exception("Unexpected exception while running IPO-RADAR from the dashboard.")
        return RadarRunFeedback(
            "error",
            "Radar run failed unexpectedly. See the application log for details.",
            tuple(message for _, message in capture.messages[-8:]),
        )
    finally:
        root_logger.removeHandler(capture)
        capture.close()

    messages = [message for _, message in capture.messages]
    errors = tuple(
        message
        for level, message in capture.messages
        if level >= logging.ERROR
    )
    if exit_code != 0:
        details = errors or tuple(messages[-8:])
        return RadarRunFeedback(
            "error",
            "Radar run failed. Review the details below and the application log.",
            details,
        )

    sent = next(
        (
            message.partition(" ")[2]
            for message in reversed(messages)
            if message.partition(" ")[2].startswith("Sent ")
            and "IPO alert" in message
        ),
        None,
    )
    if sent:
        return RadarRunFeedback("success", f"Radar completed successfully. {sent}", ())
    if any("Telegram test message sent." in message for message in messages):
        return RadarRunFeedback("success", "Radar completed: Telegram test message sent.", ())
    if any("No unsent IPOs met all alert conditions." in message for message in messages):
        return RadarRunFeedback(
            "info",
            "Radar completed. No new IPOs met all alert criteria.",
            (),
        )
    return RadarRunFeedback(
        "success",
        "Radar completed successfully. No new alerts were sent.",
        (),
    )
