[![Daily IPO-RADAR](https://github.com/akm-2610/IPO-RADAR/actions/workflows/daily.yml/badge.svg)](https://github.com/akm-2610/IPO-RADAR/actions/workflows/daily.yml)
[![CodeQL](https://github.com/akm-2610/IPO-RADAR/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/akm-2610/IPO-RADAR/actions/workflows/github-code-scanning/codeql)
[![Dependency Graph](https://github.com/akm-2610/IPO-RADAR/actions/workflows/dependabot/update-graph/badge.svg)](https://github.com/akm-2610/IPO-RADAR/actions/workflows/dependabot/update-graph)

# IPO-RADAR

IPO-RADAR checks current IPO data and sends a Telegram alert only when **all**
configured conditions are met:

- IPO is currently open: `open_date <= today <= close_date` (India Standard Time)
- QIB subscription is greater than 5x
- Retail subscription is greater than 2x
- Overall subscription is greater than 10x
- GMP is greater than 20% of the issue price

The GMP percentage is calculated as `GMP / issue price * 100`. For a price
band, the upper end is used. IPOs missing a GMP, issue price, open date, close
date, or subscription value are not eligible for an alert. Once an alert is
successfully sent for an IPO, its name and open date are recorded in
`alerts_sent.json` and it will not alert again.

## Data sources

Chittorgarh is the primary source. IPO Watch is queried only if Chittorgarh
cannot be read or has no currently open IPOs. Results are never merged. If a
source does not publish a required value, that value remains unknown and the
IPO will not trigger an alert.

## Setup

Requires Python 3.11 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`. `python main.py` loads the project `.env` before reading
any environment variables. Variables already set in the process environment
take precedence over `.env` values. Never commit real bot credentials.

To test Telegram delivery without scraping or applying IPO filters, set
`TEST_MODE=true` in `.env`. Running `python main.py` then sends one test
message and exits. Set it back to `false` to resume normal daily processing.

```powershell
$env:TELEGRAM_BOT_TOKEN = "your-bot-token"
$env:TELEGRAM_CHAT_ID = "your-chat-id"
python main.py
```

The application uses Python logging. Set `LOG_LEVEL` to `DEBUG`, `INFO`,
`WARNING`, or `ERROR` to change verbosity. Logs continue to appear on the
console and are also appended to `logs/ipo_radar.log`; the `logs` directory is
created automatically. Log entries include scraper results, filtering reasons,
sent alerts, and errors.

## Security

- `.env` and local logs are excluded from Git; use GitHub Actions secrets in CI.
- Scraper requests require HTTPS and are limited to Chittorgarh and IPO Watch,
  including redirect destinations.
- GitHub Actions pins external actions to commit SHAs and exposes its write
  token only to the alert-history persistence step.
- Scraped IPO names are stripped of control characters before they are logged
  or included in Telegram messages.

## GitHub Actions

The `.github/workflows/daily.yml` workflow is scheduled daily at 10:30 UTC
(4:00 PM IST). GitHub may delay scheduled workflows
unpredictably, so exact delivery time is not guaranteed.
Add the repository secrets `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` in **Settings → Secrets and variables → Actions**. A manual
`workflow_dispatch` trigger is also available. The workflow commits updates to
`alerts_sent.json` so duplicate prevention persists across its ephemeral
runners; repository contents write permission is required.

## Self-hosted dashboard

The private Streamlit terminal includes the market board, eligibility rules,
GMP analytics, Telegram delivery history, health probes, live log tail,
persistent settings, and a transparent baseline IPO score. It uses the current
scraper pipeline and Telegram integration rather than a second data source.

```text
IPO-RADAR/
├── dashboard.py                 # Responsive Streamlit application
├── dashboard_data.py            # DataFrame and snapshot formatting
├── services/
│   ├── ipo_service.py           # Eligibility and lifecycle status
│   ├── scraper_service.py       # Existing source orchestration
│   ├── telegram_service.py      # Bot test and resend actions
│   ├── settings.py              # Validated JSON settings
│   ├── github_actions.py        # Optional Actions API/config/status
│   ├── state_store.py           # Snapshot, event, and health persistence
│   ├── health.py                # Telegram, internet, Actions probes
│   └── scoring.py               # Replaceable baseline scoring interface
├── charts/ipo_charts.py         # Plotly visualizations
├── config/settings.json         # Thresholds and refresh policy
├── data/                        # Local snapshots and alert events
├── assets/radar-mark.svg        # Brand mark
├── pages/README.md              # UI module map
├── .streamlit/config.toml       # Dark theme and Tailscale bind address
└── logs/ipo_radar.log           # Append-only application log
```

### Windows setup

Use the same Python environment that installs the project requirements:

```powershell
cd E:\Projects\IPO-RADAR
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
python -m streamlit run dashboard.py --server.address 0.0.0.0
```

Streamlit reads `.streamlit/config.toml` automatically. The configured
`0.0.0.0:8501` bind allows Tailscale devices to connect. Start with **Sync now**
to fetch the live IPOs; subsequent data refreshes follow the saved refresh
interval. GMP history accumulates from successful refresh snapshots. Data not
provided by a source (including sector/issue size) is shown as unavailable
rather than inferred.

### Private phone access with Tailscale

1. Install Tailscale on the Windows laptop and phone, sign both into the same
   tailnet, and confirm both devices are approved.
2. Start the dashboard using the command above.
3. On the laptop, run `tailscale ip -4` and note its `100.x.x.x` address.
4. On the phone with Tailscale connected, open `http://100.x.x.x:8501`.
5. Restrict Windows Firewall inbound TCP `8501` to the tailnet range; run
   PowerShell as Administrator:

   ```powershell
   New-NetFirewallRule -DisplayName "IPO RADAR over Tailscale" `
     -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8501 `
     -RemoteAddress 100.64.0.0/10 -Profile Any
   ```

   Check existing firewall policy before adding broad rules. Do not configure
   router port forwarding or expose port 8501 to the public internet. Tailnet
   ACLs can further limit access to your own devices.

### Operations and configuration

- `config/settings.json` stores GMP, QIB, Retail, Overall, alert-frequency,
  and data-refresh thresholds. The Settings tab validates and persists edits;
  the daily GitHub runner uses the same file after those changes are pushed.
- Alert frequency is `once_per_ipo` (default), `daily`, or `weekly`. The
  duplicate-prevention ledger remains separate from the dashboard's clearable
  delivery-event list.
- `data/ipo_snapshots.jsonl` supports GMP trends; `data/alert_events.jsonl`
  stores delivered/test/resend events; `data/system_health.json` stores the
  last health check. Snapshots and health are local runtime data and excluded
  from Git. Daily Actions commits the duplicate ledger and delivery events.
- GitHub Actions monitoring is pinned to `akm-2610/IPO-RADAR`; there is no
  repository selector in the dashboard. The launcher and dashboard set
  `GITHUB_REPOSITORY` to this repository. Public access needs no token. For
  private access, configure `GITHUB_TOKEN` with Actions read permission in the
  local `.env`; the Settings tab only manages this token. Tokens are masked
  and never shown in the status panel. Missing settings show an informational
  card; API errors, invalid tokens, and rate limits are shown as status
  messages without stopping the rest of the dashboard.
- The IPO score is a transparent baseline weighted from GMP and subscription
  data. It requires all four signals; sector demand and listing gains are not
  currently available. It is not investment advice.
- `data/sample_ipo_data.csv` is clearly labeled synthetic demo data and is
  never merged into live results.

## Tests

Run offline unit tests with:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

Scraping relies on the public pages' HTML structure and may need maintenance if
those sites change. IPO Watch may not publish live subscription metrics; in
that case those metrics remain unknown and the strict alert filter suppresses
the message.
