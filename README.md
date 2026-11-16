# MIU Routine Monitor & Interactive Telegram Assistant

Automated class routine monitor, change detector, and interactive Telegram bot for **Manarat International University (MIU)** (CSE Batch 71).

Monitors the official university Google Sheets timetable, extracts scheduled sessions, detects changes (rescheduled times, room shifts, cancellations), broadcasts announcements to Telegram groups, sends daily health logs to the administrator, and provides interactive, non-cluttering routine lookups.

---

## Architecture: Hybrid Edge Model

```
┌────────────────────────────────┐         ┌────────────────────────────────┐
│  Google Sheets University Grid │         │  Telegram Group & Private DMs  │
└───────────────┬────────────────┘         └───────────────▲────────────────┘
                │ (every 3h cron)                          │
                ▼                                          │ (broadcast updates)
┌────────────────────────────────┐                         │
│ GitHub Actions (Python Runner) ├─────────────────────────┤
│  • openpyxl .xlsx parsing      │                         │ (24h admin status)
│  • Content SHA-256 diffing     │                         │
│  • Commits state/batch71.json  │                         ▼
└───────────────┬────────────────┘              ┌──────────────────────┐
                │                               │ Admin Personal Chat  │
                ▼ (raw JSON)                    └──────────────────────┘
┌────────────────────────────────┐                         ▲
│ Cloudflare Worker (Edge API)   ├─────────────────────────┘
│  • Sub-50ms Telegram Webhook   │  (Private popup alerts & DMs)
│  • Inline button modals        │
│  • Zero-clutter group commands │
└────────────────────────────────┘
```

### Why Both GitHub Actions & Cloudflare Worker?
- **GitHub Actions (Scheduled Backend):** Handles heavy `.xlsx` binary spreadsheet parsing, merged cells, teacher abbreviation tables, and diff computation via Python without needing a 24/7 dedicated server. State is committed directly to git for free, transparent version history.
- **Cloudflare Worker (Interactive Frontend):** Handles instant, sub-50ms Telegram Webhook responses 24/7 for free. When students in a group tap `[Today's Classes]`, the Worker reads `state/batch71.json` and opens an **ephemeral modal popup visible only to that user**, keeping the group 100% spam-free.

---

## Features

- **Dynamic Spreadsheet Extraction:** Scans table headers, room assignments, day partitions, and time slots dynamically without relying on hardcoded cell coordinates.
- **Merged Cell & Legend Resolution:** Handles multi-period lab blocks spanning merged cells and resolves teacher abbreviations (e.g., `BT` → `Bushra Tasnim`) from the sheet's legend.
- **Smart Content-Based Diffing:** Uses a SHA-256 hash of actual cell contents and spans (ignoring Google Sheets' fluctuating XLSX export timestamps) to detect true timetable changes.
- **Private / Ephemeral Group Lookups:** Interactive buttons trigger `show_alert: true` popups on the user's screen — zero clutter in Telegram groups!
- **Daily 24-Hour Admin Health Report:** Sends an automated 24-hour summary directly to your private chat (`admin_chat_id`), reporting total checks, successful parses, updates broadcasted, errors, and system health.
- **Weekly Hour Validation:** Compares actual routine class hours with expected weekly hours configured in `courses.json` and flags discrepancies.
- **Multi-Chat Broadcasts:** Pushes routine update announcements to both individual chats and university group chats simultaneously.

---

## Project Structure

```
MIUroutine/
├── .github/workflows/
│   └── check_routine.yml    # GitHub Actions workflow for scheduled checks
├── config.json              # Sheet ID, target tab, batch, and admin chat ID
├── courses.json             # Course catalog, credits, and expected weekly hours
├── diff.py                  # Diffs session lists and formats HTML messages
├── grid.py                  # Parses .xlsx data into memory and hashes content
├── main.py                  # CLI runner, diff engine, and 24h health reporter
├── requirements.txt         # Python dependencies (openpyxl)
├── routine.py               # Dynamic schedule and teacher legend parser
├── state.py                 # Atomic state management and history logger
├── telegram.py              # Lightweight stdlib Telegram Bot API client
├── tests/                   # Unit test suite
├── worker/
│   ├── worker.js            # Cloudflare Worker Telegram webhook handler
│   └── wrangler.toml        # Wrangler configuration
└── terraform/
    ├── main.tf              # Cloudflare Worker deployment
    ├── providers.tf         # Cloudflare provider configuration
    ├── variables.tf         # Terraform input variables
    ├── outputs.tf           # Deployed worker & webhook URLs
    └── terraform.tfvars.example
```

---

## Local Quickstart

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/snowfox-rubait/MIUroutine.git
cd MIUroutine

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Preview Current Schedule

View the parsed schedule directly in the terminal without modifying state or sending messages:

```bash
python main.py --print-schedule
```

### 3. Dry-Run & Daily Health Report

Simulate an update check or preview the 24-hour administrator report:

```bash
python main.py --dry-run
python main.py --dry-run --daily-report
```

---

## CLI Options

| Flag | Description |
| --- | --- |
| `-p`, `--print-schedule` | Print current schedule to stdout and exit |
| `-n`, `--dry-run` | Run without saving state or sending Telegram messages |
| `--daily-report` | Force send the 24-hour daily health report to admin |
| `--force` | Force a Telegram notification even if routine is unchanged |
| `-c`, `--config <path>` | Custom path to `config.json` |
| `--courses <path>` | Custom path to `courses.json` |
| `-f`, `--file <path>` | Parse a local `.xlsx` file instead of downloading from Google Sheets |

---

## GitHub Actions Setup (Scheduled Checker)

The scheduled GitHub Action in `.github/workflows/check_routine.yml` checks the spreadsheet every 3 hours.

### Repository Secrets

Navigate to **Settings > Secrets and variables > Actions** in your GitHub repository and add:

- `TELEGRAM_BOT_TOKEN`: Your bot token from [@BotFather](https://t.me/BotFather).
- `TELEGRAM_CHAT_ID`: Comma-separated list of target chat IDs (e.g. `8761332020,-1001234567890` for private chat and group).
- `TELEGRAM_ADMIN_CHAT_ID`: (Optional) Your personal chat ID for the 24h health report. Defaults to `admin_chat_id` in `config.json`.

Ensure **Workflow permissions** under **Settings > Actions > General** are set to **Read and write permissions** so the runner can commit state updates.

---

## Interactive Telegram Bot (Cloudflare Worker)

The Cloudflare Worker in `worker/worker.js` provides instant 24/7 interactive features:
- **In Groups:** Users tap `[📅 Today's Classes]` or `[📆 Tomorrow]` and an ephemeral modal dialog pops up on their screen with their schedule. No spam in the group!
- **In DMs:** Users can type `/start`, `/today`, `/tomorrow`, or `/week` and receive instant timetable cards.

### Deploying with Terraform

1. Navigate to the `terraform/` directory:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   ```
2. Fill in your Cloudflare credentials and Telegram Bot Token in `terraform.tfvars`:
   ```hcl
   cloudflare_email      = "your_email@example.com"
   cloudflare_api_key    = "your_global_api_key"
   cloudflare_account_id = "your_account_id"
   cloudflare_zone_id    = "your_zone_id"        # Leave empty if using workers.dev
   domain                = "snowfox.live"
   subdomain             = "routine"
   telegram_bot_token    = "9131553264:AAEAldBC..."
   ```
3. Initialize and apply:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```
4. Register the webhook with Telegram by visiting:
   ```
   https://routine.snowfox.live/setup-webhook
   ```

*(Alternatively, deploy with `cd worker && npx wrangler deploy`).*

---

## Configuration

### `config.json`

```json
{
  "sheet_id": "1Rhg08lM7rQF5QfDeILgF91BlTMhFc1eJpAdes9GPvX4",
  "sheet_tab": "Fall 26",
  "batch": "71",
  "state_file": "state/batch71.json",
  "history_file": "state/history.log",
  "admin_chat_id": "8761332020",
  "fetch_failures_before_alert": 3,
  "heartbeat_days": 7
}
```

---

## License

MIT
