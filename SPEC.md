# IPO-RADAR

Run daily at 4 PM IST using GitHub Actions.

Collect IPO data from:

1. Chittorgarh
2. IPO Watch (backup)

Extract:

* IPO Name
* GMP
* QIB Subscription
* Retail Subscription
* Overall Subscription
* Close Date

Alert Criteria:

Closing Today
QIB > 5x
Retail > 2x
Overall > 10x
GMP > 20%

If matched:
Send Telegram Alert

If no match:
Do nothing

Environment Variables:

TELEGRAM\_BOT\_TOKEN
TELEGRAM\_CHAT\_ID

Requirements:

* Python
* Logging
* Error handling
* GitHub Actions workflow

