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

## GitHub Actions

The `.github/workflows/daily.yml` workflow runs every day at 4:00 PM IST
(10:30 UTC). Add the repository secrets `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` in **Settings → Secrets and variables → Actions**. A manual
`workflow_dispatch` trigger is also available. The workflow commits updates to
`alerts_sent.json` so duplicate prevention persists across its ephemeral
runners; repository contents write permission is required.

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