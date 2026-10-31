# Dashboard sections

The IPO-RADAR interface keeps its monitoring modules in one responsive Streamlit
view, with tabs for the Market Board, GMP Analytics, Eligibility, Alert Center,
System Health, Log Stream, Settings, and IPO Score. This avoids separate page
state and keeps the mobile navigation compact.

Reusable data formatting lives in `dashboard_data.py`; visualizations are in
`charts/`; scraper, Telegram, health, score, settings, and persistence logic
lives under `services/`.
