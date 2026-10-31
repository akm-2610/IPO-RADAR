import logging

from services.radar_runner import run_radar_with_feedback


def test_successful_run_without_alerts_returns_visible_info():
    logger = logging.getLogger("ipo_radar.test")
    previous_level = logger.level
    logger.setLevel(logging.INFO)

    def runner():
        logger.info("No unsent IPOs met all alert conditions.")
        return 0

    try:
        feedback = run_radar_with_feedback(runner)
    finally:
        logger.setLevel(previous_level)

    assert feedback.level == "info"
    assert feedback.message == "Radar completed. No new IPOs met all alert criteria."


def test_successful_alert_run_includes_alert_count():
    logger = logging.getLogger("ipo_radar.test")
    previous_level = logger.level
    logger.setLevel(logging.INFO)

    def runner():
        logger.info("Sent 2 IPO alert(s).")
        return 0

    try:
        feedback = run_radar_with_feedback(runner)
    finally:
        logger.setLevel(previous_level)

    assert feedback.level == "success"
    assert "Sent 2 IPO alert(s)" in feedback.message


def test_failed_run_surfaces_error_details():
    logger = logging.getLogger("ipo_radar.test")
    previous_level = logger.level
    logger.setLevel(logging.INFO)

    def runner():
        logger.error("Telegram credentials are missing.")
        return 1

    try:
        feedback = run_radar_with_feedback(runner)
    finally:
        logger.setLevel(previous_level)

    assert feedback.level == "error"
    assert feedback.details == ("ERROR Telegram credentials are missing.",)


def test_unexpected_exception_becomes_visible_failure():
    feedback = run_radar_with_feedback(
        lambda: (_ for _ in ()).throw(RuntimeError("unexpected"))
    )

    assert feedback.level == "error"
    assert "failed unexpectedly" in feedback.message
