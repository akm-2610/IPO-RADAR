from datetime import date, datetime
from decimal import Decimal

import pytest

from alert_history import JSONAlertHistory
from dashboard_data import build_ipo_table, snapshots_to_frame
from models import IPO
from services.scoring import BaselineIPOScorer
from services.settings import RadarSettings, SettingsError, load_settings, save_settings
from services.state_store import DashboardState, ipo_from_dict


def _sample_ipo(**changes):
    values = {
        "name": "Northstar Components",
        "gmp": Decimal("30"),
        "issue_price": Decimal("100"),
        "qib_subscription": Decimal("8"),
        "retail_subscription": Decimal("4"),
        "overall_subscription": Decimal("20"),
        "open_date": date(2026, 10, 30),
        "close_date": date(2026, 11, 2),
        "issue_size": "₹840 Cr",
        "price_band": "₹125-132",
        "sector": "Industrials",
    }
    values.update(changes)
    return IPO(**values)


def test_settings_are_saved_and_loaded_with_validation(tmp_path):
    path = tmp_path / "config" / "settings.json"
    expected = RadarSettings(alert_frequency="weekly", refresh_interval_seconds=600)

    save_settings(path, expected)

    assert load_settings(path) == expected


def test_invalid_settings_raise_an_explicit_error(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"alert_frequency": "hourly"}', encoding="utf-8")

    with pytest.raises(SettingsError):
        load_settings(path)


def test_snapshots_and_alert_events_are_persisted(tmp_path):
    state = DashboardState(tmp_path / "data")
    ipo = _sample_ipo()
    captured = datetime.fromisoformat("2026-10-31T16:00:00+05:30")

    state.record_snapshot([ipo], source="Chittorgarh", captured_at=captured)
    state.record_alert(ipo=ipo, message="test alert", status="sent", timestamp=captured)

    snapshot = state.read_snapshots()[0]
    restored = ipo_from_dict(snapshot["ipos"][0])
    assert restored == ipo
    assert state.read_alerts()[0]["ipo_name"] == ipo.name
    assert not snapshots_to_frame(state.read_snapshots()).empty


def test_clearing_dashboard_events_does_not_change_duplicate_ledger(tmp_path):
    state = DashboardState(tmp_path / "data")
    ipo = _sample_ipo()
    ledger = JSONAlertHistory(tmp_path / "alerts_sent.json")
    ledger.record_alert(ipo, date(2026, 10, 31))
    state.record_alert(ipo=ipo, message="test alert", status="sent")

    state.clear_alerts()

    assert state.read_alerts() == []
    assert (tmp_path / "data" / "alert_events.jsonl").read_text(encoding="utf-8") == ""
    assert JSONAlertHistory(tmp_path / "alerts_sent.json").has_alerted(ipo)


def test_score_requires_complete_signal_data():
    scorer = BaselineIPOScorer()

    result = scorer.score(_sample_ipo())
    incomplete = scorer.score(_sample_ipo(retail_subscription=None))

    assert result.score is not None
    assert result.label in {"Strong Buy", "Watchlist", "Avoid"}
    assert incomplete.score is None
    assert incomplete.label == "Not rated"


def test_table_contains_monitoring_fields_and_rule_status():
    table = build_ipo_table(
        [_sample_ipo()],
        today=date(2026, 10, 31),
        settings=RadarSettings(),
    )

    row = table.iloc[0]
    assert row["Issue Size"] == "₹840 Cr"
    assert row["Price Band"] == "₹125-132"
    assert row["Eligibility Status"] == "Eligible"
    assert row["Days Remaining"] == 2
