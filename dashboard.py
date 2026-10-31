"""Self-hosted IPO-RADAR monitoring terminal."""

from __future__ import annotations

import html
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from alert_history import AlertHistoryError, JSONAlertHistory
from charts.ipo_charts import (
    COLORS,
    gmp_histogram,
    gmp_leaderboard,
    gmp_trend,
    sector_heatmap,
)
from dashboard_data import build_ipo_table, snapshots_to_frame
from filters.alerts import alert_rejection_reasons
from main import PROJECT_ROOT, configure_logging, format_alert
from models import IPO
from notifier.telegram import TelegramNotificationError
from scrapers.base import ScrapeError
from services.health import check_system_health
from services.ipo_service import current_status, rejection_reasons
from services.scoring import BaselineIPOScorer
from services.scraper_service import fetch_open_ipos
from services.settings import RadarSettings, SettingsError, load_settings, save_settings
from services.state_store import (
    DashboardState,
    StateStoreError,
    ipo_from_dict,
    ipo_to_dict,
)
from services.telegram_service import TelegramService

IST = ZoneInfo("Asia/Kolkata")
LOGGER = logging.getLogger("ipo_radar.dashboard")
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"
DATA_PATH = PROJECT_ROOT / "data"
LOG_PATH = PROJECT_ROOT / "logs" / "ipo_radar.log"
TEST_MESSAGE = "✅ IPO-RADAR TEST MESSAGE\n\nTelegram integration is working."

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
st.set_page_config(
    page_title="IPO RADAR | Market Monitor",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
configure_logging()

st.markdown(
    """
    <style>
    :root {
      --radar-bg: #0e1117; --radar-panel: #151a23; --radar-line: #252c38;
      --radar-green: #16c784; --radar-red: #ea3943; --radar-blue: #3861fb;
      --radar-ink: #e6eaf0; --radar-muted: #8993a4;
    }
    html, body, [class*="css"] { font-family: 'Bahnschrift', 'Segoe UI', sans-serif; }
    .stApp { background:
      radial-gradient(ellipse at 82% 0%, rgba(22,199,132,.07), transparent 34%),
      linear-gradient(180deg, #0e1117 0%, #0c0f14 100%); color: var(--radar-ink); }
    [data-testid="stHeader"] { background: rgba(14,17,23,.88); }
    [data-testid="stMetric"] {
      background: linear-gradient(145deg, rgba(21,26,35,.98), rgba(17,21,29,.92));
      border: 1px solid var(--radar-line); border-radius: 12px;
      padding: 15px 17px; min-height: 116px;
    }
    [data-testid="stMetricLabel"] p {
      color: var(--radar-muted); font: 500 11px 'Consolas', monospace;
      text-transform: uppercase; letter-spacing: .11em;
    }
    [data-testid="stMetricValue"] { font: 700 25px 'Consolas', monospace; }
    [data-testid="stMetricDelta"] { font: 500 11px 'Consolas', monospace; }
    .radar-topbar {
      display:flex; align-items:center; justify-content:space-between; gap:16px;
      border:1px solid var(--radar-line); border-radius:14px; padding:16px 20px;
      margin:2px 0 20px; background:rgba(21,26,35,.88);
      box-shadow:0 12px 40px rgba(0,0,0,.18);
    }
    .radar-brand { display:flex; align-items:center; gap:12px; }
    .radar-mark { color:var(--radar-green); font-size:24px; }
    .radar-title { font-size:18px; font-weight:800; letter-spacing:.16em; }
    .radar-subtitle { color:var(--radar-muted); font:10px 'Consolas',monospace; letter-spacing:.12em; }
    .radar-meta { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:9px; }
    .radar-chip { border:1px solid var(--radar-line); padding:7px 10px; border-radius:20px;
      color:var(--radar-muted); font:10px 'Consolas',monospace; white-space:nowrap; }
    .radar-dot { color:var(--radar-green); }
    .section-kicker { color:var(--radar-green); font:11px 'Consolas',monospace;
      letter-spacing:.16em; text-transform:uppercase; }
    .email-card { border:1px solid var(--radar-line); border-left:3px solid var(--radar-blue);
      border-radius:10px; padding:17px 19px; background:#121720; margin:10px 0; }
    .email-card .email-heading { color:var(--radar-green); font:500 11px 'Consolas',monospace;
      letter-spacing:.1em; margin-bottom:12px; }
    .email-card .email-content { color:#dce2eb; font:13px/1.8 'Consolas',monospace;
      white-space:pre-wrap; }
    div[data-testid="stTabs"] button { font:600 12px 'Consolas',monospace; }
    div[data-testid="stTabs"] button[aria-selected="true"] { color:var(--radar-green); }
    div[data-testid="stDataFrame"] { border:1px solid var(--radar-line); border-radius:10px; }
    .small-note { color:var(--radar-muted); font-size:12px; }
    @media (max-width: 700px) {
      .radar-topbar { align-items:flex-start; flex-direction:column; padding:14px; }
      .radar-meta { justify-content:flex-start; }
      .radar-title { font-size:16px; }
      [data-testid="stMetric"] { min-height:98px; padding:11px; }
      [data-testid="stMetricValue"] { font-size:20px; }
      div[data-testid="stHorizontalBlock"] { gap:.45rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    settings = load_settings(SETTINGS_PATH)
except SettingsError as error:
    st.error(f"Could not load dashboard settings: {error}")
    st.stop()

state = DashboardState(DATA_PATH)
telegram = TelegramService()
today = datetime.now(IST).date()


def _format_value(value: object, suffix: str) -> str:
    if value is None:
        return "Unavailable"
    return f"{value}{suffix}"


def _read_log_tail(path: Path, *, max_bytes: int) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as source:
        source.seek(0, os.SEEK_END)
        end = source.tell()
        source.seek(max(0, end - max_bytes))
        return source.read(max_bytes).decode("utf-8", errors="replace")


def _restored_ipos() -> tuple[list[IPO], datetime | None, str]:
    try:
        snapshots = state.read_snapshots(limit=500)
    except StateStoreError as error:
        LOGGER.error("Unable to restore dashboard IPO snapshots: %s", error)
        return [], None, "Unavailable"
    latest_by_key: dict[tuple[str, date | None], IPO] = {}
    last_refresh: datetime | None = None
    latest_source = "Unknown"
    for snapshot in snapshots:
        try:
            captured = datetime.fromisoformat(snapshot["timestamp"])
            if last_refresh is None or captured > last_refresh:
                last_refresh = captured
                latest_source = str(snapshot.get("source", "Unknown"))
            for raw in snapshot.get("ipos", []):
                ipo = ipo_from_dict(raw)
                latest_by_key[(ipo.name.casefold(), ipo.open_date)] = ipo
        except (KeyError, TypeError, ValueError):
            LOGGER.warning("Skipping malformed IPO snapshot in dashboard state.")
    return list(latest_by_key.values()), last_refresh, latest_source


if "records" not in st.session_state:
    records, restored_at, source_name = _restored_ipos()
    st.session_state.records = records
    st.session_state.last_refresh = restored_at
    st.session_state.source_name = source_name
    st.session_state.scraper_status = "Not checked"


def _refresh_data(*, show_success: bool = True) -> bool:
    try:
        fresh_records = fetch_open_ipos(datetime.now(IST).date())
        state.record_snapshot(fresh_records, source="Chittorgarh / IPO Watch")
        st.session_state.records = fresh_records
        st.session_state.last_refresh = datetime.now(IST)
        sources = {
            "Chittorgarh" if "chittorgarh" in (ipo.source_url or "") else "IPO Watch"
            for ipo in fresh_records
            if ipo.source_url
        }
        st.session_state.source_name = ", ".join(sorted(sources)) or "No active IPOs"
        st.session_state.scraper_status = "Healthy"
        if show_success:
            st.toast(f"Loaded {len(fresh_records)} currently open IPOs.", icon="✅")
        _update_health()
        return True
    except (ScrapeError, StateStoreError) as error:
        st.session_state.scraper_status = "Failure"
        LOGGER.exception("Dashboard data refresh failed.")
        st.error(f"IPO data refresh failed: {error}")
        return False


def _update_health() -> None:
    try:
        events = state.read_alerts(limit=1000)
        success_events = [event for event in events if event.get("status") == "sent"]
        health = check_system_health(
            telegram=telegram,
            scraper_status=st.session_state.get("scraper_status", "Not checked"),
            last_scraper_run=(
                st.session_state.last_refresh.isoformat()
                if st.session_state.get("last_refresh")
                else None
            ),
            last_successful_alert=success_events[-1].get("timestamp") if success_events else None,
        )
        state.write_health(health)
    except (StateStoreError, OSError) as error:
        LOGGER.error("Unable to update system health: %s", error)


if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None
if "scraper_status" not in st.session_state:
    st.session_state.scraper_status = "Not checked"

last_refresh_text = (
    st.session_state.last_refresh.strftime("%d %b %Y · %H:%M IST")
    if st.session_state.last_refresh
    else "Awaiting first sync"
)
bot_status = "Configured" if telegram.configured else "Needs credentials"
source_text = st.session_state.get("source_name", "Not checked")
st.markdown(
    f"""
    <div class="radar-topbar">
      <div class="radar-brand">
        <div class="radar-mark">◉</div>
        <div><div class="radar-title">IPO RADAR</div>
          <div class="radar-subtitle">PRIMARY MARKET INTELLIGENCE · IST</div></div>
      </div>
      <div class="radar-meta">
        <span class="radar-chip">SYNC · {html.escape(last_refresh_text)}</span>
        <span class="radar-chip"><span class="radar-dot">●</span> BOT · {html.escape(bot_status)}</span>
        <span class="radar-chip">DATA · {html.escape(source_text)}</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

records: list[IPO] = st.session_state.records
history_names: set[str] = set()
try:
    events = state.read_alerts(limit=1000)
    history_names = {
        str(event.get("ipo_name", "")).casefold()
        for event in events
        if event.get("status") == "sent"
    }
except StateStoreError as error:
    events = []
    st.warning(f"Alert event history is unavailable: {error}")

try:
    duplicate_history = JSONAlertHistory(PROJECT_ROOT / "alerts_sent.json")
except AlertHistoryError as error:
    duplicate_history = None
    st.warning(f"Duplicate-alert ledger is unavailable: {error}")
alerted_names = set(history_names)
if duplicate_history is not None:
    alerted_names.update(ipo.name.casefold() for ipo in records if duplicate_history.has_alerted(ipo))

table = build_ipo_table(
    records,
    today=today,
    settings=settings,
    last_alerted=alerted_names,
)
eligible_count = int((table["Eligibility Status"] == "Eligible").sum()) if not table.empty else 0
active_count = int((table["Status"] == "Open").sum()) if not table.empty else 0
gmp_count = (
    int((table["GMP %"].fillna(-1) > settings.gmp_threshold_pct).sum())
    if not table.empty
    else 0
)
sent_today = sum(
    1
    for event in events
    if event.get("status") in {"sent", "resent"}
    and str(event.get("timestamp", "")).startswith(today.isoformat())
    and str(event.get("message", "")).startswith("🚨 IPO ALERT")
)
highest_gmp = table.dropna(subset=["GMP %"]).sort_values("GMP %", ascending=False).head(1)
highest_label = (
    f"{highest_gmp.iloc[0]['IPO Name']} · {highest_gmp.iloc[0]['GMP %']:.1f}%"
    if not highest_gmp.empty
    else "No GMP data"
)
prior_snapshot_records: list[IPO] = []
try:
    recent_snapshots = state.read_snapshots(limit=2)
    if len(recent_snapshots) > 1:
        prior_snapshot_records = [
            ipo_from_dict(raw) for raw in recent_snapshots[-2].get("ipos", [])
        ]
except (StateStoreError, KeyError, TypeError, ValueError):
    prior_snapshot_records = []
prior_table = build_ipo_table(
    prior_snapshot_records,
    today=today,
    settings=settings,
)


def _trend_delta(current: int, prior: int | None) -> str:
    return f"{current - prior:+d} vs prior sync" if prior is not None else "first sync"


prior_active = int((prior_table["Status"] == "Open").sum()) if not prior_table.empty else None
prior_eligible = (
    int((prior_table["Eligibility Status"] == "Eligible").sum())
    if not prior_table.empty
    else None
)
prior_gmp = (
    int((prior_table["GMP %"].fillna(-1) > settings.gmp_threshold_pct).sum())
    if not prior_table.empty
    else None
)
st.markdown('<div class="section-kicker">01 / Market overview</div>', unsafe_allow_html=True)
metric_columns = st.columns(3)
metric_columns[0].metric("Active IPOs", active_count, delta=_trend_delta(active_count, prior_active))
metric_columns[1].metric("Eligible", eligible_count, delta=_trend_delta(eligible_count, prior_eligible))
metric_columns[2].metric(
    "GMP above threshold",
    gmp_count,
    delta=_trend_delta(gmp_count, prior_gmp),
)
metric_columns = st.columns(3)
metric_columns[0].metric("Alerts sent today", sent_today, delta="since midnight IST")
metric_columns[1].metric("Highest GMP", highest_label, delta=f"threshold {settings.gmp_threshold_pct:g}%")
metric_columns[2].metric(
    "Last successful update",
    st.session_state.last_refresh.strftime("%H:%M") if st.session_state.last_refresh else "—",
    delta="IST",
)

overview, analytics, eligibility, alerts_tab, health_tab, logs_tab, settings_tab, score_tab = st.tabs(
    [
        "MARKET BOARD",
        "GMP ANALYTICS",
        "ELIGIBILITY",
        "ALERT CENTER",
        "SYSTEM HEALTH",
        "LOG STREAM",
        "SETTINGS",
        "IPO SCORE",
    ]
)


def _style_rows(frame: pd.DataFrame) -> pd.io.formats.style.Styler:
    def row_style(row: pd.Series) -> list[str]:
        if row.get("Status") == "Expired":
            color = "rgba(234, 57, 67, .17)"
        elif row.get("Eligibility Status") == "Eligible":
            color = "rgba(22, 199, 132, .14)"
        else:
            color = ""
        return [f"background-color: {color}" if color else "" for _ in row]

    return frame.style.apply(row_style, axis=1).format(
        {"GMP %": lambda value: f"{value:.2f}%" if pd.notna(value) else "N/A"}
    )


with overview:
    left, right = st.columns([1.3, 1])
    with left:
        search_text = st.text_input("Search IPO", placeholder="Name, source, sector…", key="ipo_search")
    with right:
        status_filter = st.selectbox("Filter status", ["All", "Open", "Upcoming", "Expired", "Eligible"])
    filtered = table.copy()
    if search_text:
        mask = filtered.astype(str).apply(
            lambda column: column.str.contains(search_text, case=False, na=False)
        ).any(axis=1)
        filtered = filtered[mask]
    if status_filter == "Eligible":
        filtered = filtered[filtered["Eligibility Status"] == "Eligible"]
    elif status_filter != "All":
        filtered = filtered[filtered["Status"] == status_filter]

    if filtered.empty:
        st.info("No IPOs match these filters. Use Sync now to fetch live issue data.")
    else:
        st.dataframe(
            _style_rows(filtered),
            width="stretch",
            hide_index=True,
            height=min(570, 44 + 36 * len(filtered)),
            column_config={
                "GMP %": st.column_config.NumberColumn(format="%.2f%%"),
                "Eligibility Reasons": st.column_config.TextColumn(width="large"),
                "IPO": st.column_config.TextColumn(width="medium"),
            },
        )
    csv = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Download filtered CSV", csv, "ipo_radar.csv", "text/csv")
    action_a, action_b = st.columns([1, 3])
    if action_a.button("↻ Sync now", type="primary", width="stretch"):
        _refresh_data()
        st.rerun()
    with action_b:
        if st.button("▶ Run radar & send eligible alerts", width="stretch"):
            try:
                with st.spinner("Running the configured scraper and alert rules..."):
                    from main import run

                    result = run()
                if result == 0:
                    _refresh_data(show_success=False)
                    st.success("Radar run completed. Review the log stream for per-IPO decisions.")
                    st.rerun()
                else:
                    st.error("Radar run failed. Review the log stream for error details.")
            except ScrapeError as error:
                st.error(f"Radar run failed: {error}")


with analytics:
    snapshots = state.read_snapshots(limit=500)
    analytics_frame = snapshots_to_frame(snapshots)
    if not analytics_frame.empty:
        min_day = analytics_frame["Timestamp"].min().date()
        max_day = analytics_frame["Timestamp"].max().date()
        selected_dates = st.date_input(
            "Snapshot date range",
            value=(min_day, max_day),
            min_value=min_day,
            max_value=max_day,
        )
        if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
            start_day, end_day = selected_dates
            analytics_frame = analytics_frame[
                analytics_frame["Timestamp"].dt.date.between(start_day, end_day)
            ]
        ipo_options = ["All IPOs"] + sorted(analytics_frame["IPO Name"].dropna().unique().tolist())
        selected_ipo = st.selectbox("IPO series", ipo_options)
        if selected_ipo != "All IPOs":
            analytics_frame = analytics_frame[analytics_frame["IPO Name"] == selected_ipo]
    else:
        st.info("GMP history starts accumulating after the first dashboard refresh.")
    live_frame = table.rename(columns={"IPO": "IPO Name"}) if not table.empty else pd.DataFrame()
    chart_frame = analytics_frame
    if chart_frame.empty and not live_frame.empty:
        chart_frame = live_frame[["IPO Name", "GMP %", "Sector"]].copy()
        chart_frame["Timestamp"] = datetime.now(IST)
    chart_left, chart_right = st.columns(2)
    chart_left.plotly_chart(gmp_leaderboard(chart_frame), width="stretch")
    chart_right.plotly_chart(gmp_histogram(chart_frame), width="stretch")
    st.plotly_chart(gmp_trend(analytics_frame), width="stretch")
    st.plotly_chart(sector_heatmap(chart_frame), width="stretch")
    st.caption("Trend history is persisted from dashboard refreshes; sectors remain unclassified when the source does not publish them.")


with eligibility:
    st.markdown("#### Active rule set")
    st.caption(
        f"Open today · QIB > {settings.qib_threshold:g}x · Retail > {settings.retail_threshold:g}x · "
        f"Overall > {settings.overall_threshold:g}x · GMP > {settings.gmp_threshold_pct:g}%"
    )
    if records:
        selected_name = st.selectbox("Inspect an IPO", [ipo.name for ipo in records], key="rule_ipo")
        selected = next(ipo for ipo in records if ipo.name == selected_name)
        rules = [
            ("IPO currently open", current_status(selected, today) == "Open", "Open date <= today <= close date"),
            (
                "QIB subscription > threshold",
                selected.qib_subscription is not None
                and selected.qib_subscription > settings.qib_threshold,
                f"Observed {_format_value(selected.qib_subscription, 'x')} · required > {settings.qib_threshold:g}x",
            ),
            (
                "Retail subscription > threshold",
                selected.retail_subscription is not None
                and selected.retail_subscription > settings.retail_threshold,
                f"Observed {_format_value(selected.retail_subscription, 'x')} · required > {settings.retail_threshold:g}x",
            ),
            (
                "Overall subscription > threshold",
                selected.overall_subscription is not None
                and selected.overall_subscription > settings.overall_threshold,
                f"Observed {_format_value(selected.overall_subscription, 'x')} · required > {settings.overall_threshold:g}x",
            ),
            (
                "GMP percentage > threshold",
                selected.gmp_percent is not None
                and selected.gmp_percent > settings.gmp_threshold_pct,
                f"Observed {_format_value(selected.gmp_percent, '%')} · required > {settings.gmp_threshold_pct:g}%",
            ),
            ("Retail category available", selected.retail_subscription is not None, "Retail subscription data must be published"),
        ]
        rule_frame = pd.DataFrame(
            [
                {"Rule Name": name, "Status": "PASS" if passed else "FAIL", "Result": detail}
                for name, passed, detail in rules
            ]
        )
        st.dataframe(
            rule_frame.style.apply(
                lambda row: [
                    "color: #16C784; font-weight: 700" if row["Status"] == "PASS"
                    else "color: #EA3943; font-weight: 700"
                    if column == "Status"
                    else ""
                    for column in row.index
                ],
                axis=1,
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No IPO data available yet.")


with alerts_tab:
    st.markdown("#### Delivery history")
    ordered_events = sorted(events, key=lambda event: str(event.get("timestamp", "")), reverse=True)
    event_rows = [
        {
            "Timestamp": event.get("timestamp", "N/A"),
            "IPO Name": event.get("ipo_name", "N/A"),
            "GMP": f"₹{event['gmp']}" if event.get("gmp") is not None else "N/A",
            "Status": str(event.get("status", "unknown")).upper(),
            "Alert Message": str(event.get("message", "")),
        }
        for event in ordered_events
    ]
    if event_rows:
        st.dataframe(pd.DataFrame(event_rows), width="stretch", hide_index=True)
        selected_event = st.selectbox(
            "Preview alert message",
            range(len(ordered_events)),
            format_func=lambda index: (
                f"{ordered_events[index].get('timestamp', 'N/A')} · "
                f"{ordered_events[index].get('ipo_name', 'IPO')}"
            ),
        )
        message = str(ordered_events[selected_event].get("message", ""))
        st.markdown(
            f'<div class="email-card"><div class="email-heading">IPO RADAR · ALERT PREVIEW</div>'
            f'<div class="email-content">{html.escape(message)}</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("Resend selected alert"):
            try:
                telegram.send(message)
            except TelegramNotificationError as error:
                st.error(f"Could not resend alert: {error}")
            else:
                event_ipo = next(
                    (ipo for ipo in records if ipo.name == ordered_events[selected_event].get("ipo_name")),
                    IPO(name=str(ordered_events[selected_event].get("ipo_name", "IPO"))),
                )
                try:
                    state.record_alert(ipo=event_ipo, message=message, status="resent")
                except StateStoreError as error:
                    st.error(f"Alert was resent, but delivery history could not be saved: {error}")
                else:
                    st.success("Alert resent through Telegram.")
    else:
        st.info("No Telegram delivery events have been recorded yet.")
    button_a, button_b = st.columns([1, 4])
    if button_a.button("Send test alert"):
        try:
            telegram.send(TEST_MESSAGE)
        except TelegramNotificationError as error:
            try:
                state.record_alert(
                    ipo=IPO(name="Telegram test"),
                    message=TEST_MESSAGE,
                    status="failed",
                )
            except StateStoreError as state_error:
                LOGGER.error("Unable to record failed Telegram test: %s", state_error)
            st.error(f"Telegram test failed: {error}")
        else:
            try:
                state.record_alert(
                    ipo=IPO(name="Telegram test"),
                    message=TEST_MESSAGE,
                    status="sent",
                )
            except StateStoreError as error:
                st.error(f"Test message was sent but delivery history could not be saved: {error}")
            else:
                st.success("Telegram test message sent.")
    with button_b:
        if st.button("Clear displayed alert history"):
            st.session_state.confirm_clear_alerts = True
        if st.session_state.get("confirm_clear_alerts"):
            st.warning("This clears the dashboard delivery-event list only. Duplicate-prevention records stay intact.")
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button("Confirm clear history", type="primary"):
                try:
                    state.clear_alerts()
                    st.session_state.confirm_clear_alerts = False
                    st.success("Dashboard alert events cleared.")
                    st.rerun()
                except StateStoreError as error:
                    st.error(f"Could not clear alert events: {error}")
            if cancel_col.button("Cancel"):
                st.session_state.confirm_clear_alerts = False


with health_tab:
    try:
        health = state.read_health()
    except StateStoreError as error:
        health = {}
        st.error(f"Could not read system health: {error}")
    if st.button("Check system health"):
        _update_health()
        st.rerun()

    def _health_badge(label: str, value: str) -> None:
        normalized = value.casefold()
        tone = "🟢" if normalized in {"healthy", "configured"} else "🔴" if normalized == "failure" else "🟡"
        st.metric(label, f"{tone} {value}")

    hc = st.columns(4)
    for column, (label, key) in zip(
        hc,
        [
            ("Telegram API", "telegram"),
            ("Scraper", "scraper"),
            ("Internet", "internet"),
            ("GitHub Actions", "github_actions"),
        ],
    ):
        with column:
            _health_badge(label, str(health.get(key, st.session_state.scraper_status if key == "scraper" else "Not checked")))
    st.write(f"Last scraper run: `{health.get('last_scraper_run') or last_refresh_text}`")
    st.write(f"Last successful alert: `{health.get('last_successful_alert') or 'No successful delivery recorded'}`")
    st.write(f"Health checked: `{health.get('checked_at', 'Not checked')}`")
    st.caption("Set GITHUB_REPOSITORY (and optionally GITHUB_TOKEN for private repositories) to inspect the latest Actions run.")


with logs_tab:
    st.markdown("#### Application log · live tail")

    @st.fragment(run_every=30)
    def render_log_viewer() -> None:
        search = st.text_input("Search log text", key="log_search")
        level = st.multiselect("Severity", ["INFO", "WARNING", "ERROR", "DEBUG"], default=["INFO", "WARNING", "ERROR"])
        try:
            log_text = _read_log_tail(LOG_PATH, max_bytes=1_000_000)
        except OSError as error:
            st.error(f"Could not read application log: {error}")
            return
        lines = log_text.splitlines()
        if level:
            lines = [line for line in lines if any(f" {selected} " in line for selected in level)]
        if search:
            lines = [line for line in lines if search.casefold() in line.casefold()]
        st.caption(f"Showing {len(lines)} matching lines · refreshes every 30 seconds · tail limited to 1 MB")
        st.code("\n".join(lines[-1000:]) or "No matching log entries.", language="text")
        st.download_button(
            "Download current log tail",
            "\n".join(lines).encode("utf-8"),
            "ipo_radar.log",
            "text/plain",
            key="download_log",
        )

    render_log_viewer()


with settings_tab:
    st.markdown("#### Persistent alert & refresh configuration")
    with st.form("radar_settings"):
        set_col_a, set_col_b = st.columns(2)
        with set_col_a:
            gmp_threshold = st.number_input("GMP threshold (%)", min_value=0.0, max_value=1000.0, value=float(settings.gmp_threshold_pct), step=1.0)
            qib_threshold = st.number_input("QIB subscription threshold (x)", min_value=0.0, max_value=10000.0, value=float(settings.qib_threshold), step=0.5)
            retail_threshold = st.number_input("Retail subscription threshold (x)", min_value=0.0, max_value=10000.0, value=float(settings.retail_threshold), step=0.5)
        with set_col_b:
            overall_threshold = st.number_input("Overall subscription threshold (x)", min_value=0.0, max_value=100000.0, value=float(settings.overall_threshold), step=1.0)
            frequency = st.selectbox(
                "Alert frequency",
                ["once_per_ipo", "daily", "weekly"],
                index=["once_per_ipo", "daily", "weekly"].index(settings.alert_frequency),
                format_func={"once_per_ipo": "Once per IPO (recommended)", "daily": "At most once daily", "weekly": "At most once weekly"}.get,
            )
            refresh_seconds = st.number_input(
                "Data refresh interval (seconds)",
                min_value=30,
                max_value=86400,
                value=settings.refresh_interval_seconds,
                step=30,
            )
        saved = st.form_submit_button("Save settings", type="primary")
    if saved:
        updated = RadarSettings(
            gmp_threshold_pct=gmp_threshold,
            qib_threshold=qib_threshold,
            retail_threshold=retail_threshold,
            overall_threshold=overall_threshold,
            alert_frequency=frequency,
            refresh_interval_seconds=int(refresh_seconds),
        )
        try:
            save_settings(SETTINGS_PATH, updated)
            st.success("Settings saved. Alert runner and dashboard use the updated thresholds.")
            st.rerun()
        except SettingsError as error:
            st.error(f"Could not save settings: {error}")
    st.caption("The GitHub Actions runner reads this same JSON configuration after the file is pushed to the repository.")


with score_tab:
    st.markdown("#### IPO score · transparent baseline")
    st.caption("A replaceable scoring interface for future ML integration. Informational signal only; not investment advice.")
    if records:
        score_rows = []
        scorer = BaselineIPOScorer()
        for ipo in records:
            result = scorer.score(ipo)
            score_rows.append(
                {
                    "IPO": ipo.name,
                    "Score": result.score if result.score is not None else "N/A",
                    "Signal": result.label,
                    "Coverage": result.explanation,
                }
            )
        st.dataframe(pd.DataFrame(score_rows), width="stretch", hide_index=True)
        st.caption("Current weighted inputs: GMP (40%), QIB (15%), Retail (15%), Overall subscription (30%). Historical listing gains and sector demand are future integrations.")
    else:
        st.info("Sync live IPO data to calculate available baseline scores.")


@st.fragment(run_every=settings.refresh_interval_seconds)
def scheduled_data_refresh() -> None:
    last_refresh = st.session_state.get("last_refresh")
    if last_refresh is None:
        return
    now = datetime.now(IST)
    if last_refresh is None or (now - last_refresh).total_seconds() >= settings.refresh_interval_seconds:
        LOGGER.info("Scheduled dashboard refresh started.")
        _refresh_data(show_success=False)


scheduled_data_refresh()
