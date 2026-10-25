from datetime import date

from alert_history import JSONAlertHistory
from models import IPO


def make_ipo(**changes):
    values = {
        "name": "Example IPO Ltd.",
        "open_date": date(2026, 10, 20),
    }
    values.update(changes)
    return IPO(**values)


def test_alert_history_prevents_duplicate_alert_after_reload(tmp_path):
    history_path = tmp_path / "alerts_sent.json"
    ipo = make_ipo()

    first_run = JSONAlertHistory(history_path)
    assert not first_run.has_alerted(ipo)
    first_run.record_alert(ipo, date(2026, 10, 25))

    next_run = JSONAlertHistory(history_path)
    assert next_run.has_alerted(ipo)


def test_alert_history_distinguishes_a_new_offering(tmp_path):
    history = JSONAlertHistory(tmp_path / "alerts_sent.json")
    history.record_alert(make_ipo(), date(2026, 10, 25))

    assert not history.has_alerted(make_ipo(open_date=date(2027, 3, 1)))


def test_alert_history_persists_sent_date(tmp_path):
    history_path = tmp_path / "alerts_sent.json"
    history = JSONAlertHistory(history_path)
    ipo = make_ipo()
    history.record_alert(ipo, date(2026, 10, 25))

    assert history_path.read_text(encoding="utf-8") == (
        '{\n  "example-ipo-ltd:2026-10-20": "2026-10-25"\n}\n'
    )
