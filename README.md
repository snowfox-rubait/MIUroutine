# MIU Routine Monitor & Telegram Notifier

Automated class routine monitor and Telegram notification bot for **Manarat International University (MIU)**.

Monitors the university's official Google Sheets class routine, extracts scheduled sessions for a specific batch (e.g. CSE Batch 71), detects schedule changes (room moves, rescheduled time slots, added/canceled classes), and broadcasts clean, formatted updates directly to a Telegram group or channel.

---

## Features

- **Dynamic Spreadsheet Extraction:** Scans table headers, room assignments, day partitions, and time slots dynamically without relying on hardcoded cell coordinates.
- **Merged Cell & Legend Resolution:** Handles multi-period lab blocks spanning merged cells and resolves teacher abbreviations (e.g., `BT` → `Bushra Tasnim`) from the sheet's legend.
- **Smart Content-Based Diffing:** Uses a SHA-256 hash of actual cell contents and spans (ignoring Google Sheets' fluctuating XLSX export timestamps) to detect true changes.
- **Intelligent Change Detection:** Pairs removed and added sessions of the same course as "Changed" (e.g. class moved to another day or room).
- **Telegram Notifications:** Sends clean, HTML-formatted schedule summaries and diffs. Automatically splits long messages across line boundaries to respect Telegram's message limits.
- **Weekly Hour Validation:** Compares actual routine class hours with expected weekly hours configured in `courses.json` and flags discrepancies.
- **Heartbeat & Failure Alerts:** Sends periodic "alive" heartbeats if no changes occur over a set duration, and alerts administrators if Google Sheets fails to fetch repeatedly.
- **Zero-Maintenance Automation:** Ready to run autonomously on GitHub Actions cron with automatic state persistence.

---

## Project Structure

```
MIUroutine/
├── .github/workflows/
│   └── check_routine.yml    # GitHub Actions workflow for scheduled checks
├── config.json              # Sheet ID, target tab, batch, and monitoring intervals
├── courses.json             # Course catalog, credits, and expected weekly hours
├── diff.py                  # Diffs session lists and formats HTML messages
├── grid.py                  # Parses .xlsx data into memory and hashes content
├── main.py                  # CLI entrypoint and orchestrator
├── requirements.txt         # Python dependencies (openpyxl)
├── routine.py               # Dynamic schedule and teacher legend parser
├── state.py                 # Atomic state management and history logger
└── telegram.py              # Lightweight stdlib Telegram Bot API client
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

### 3. Dry-Run Check

Simulate an update check and view what would be sent to Telegram:

```bash
python main.py --dry-run
```

### 4. Run Locally with Telegram

Set your Telegram credentials and run:

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"   # Comma-separated for multiple chats

python main.py
```

---

## CLI Options

| Flag | Description |
| --- | --- |
| `-p`, `--print-schedule` | Print current schedule to stdout and exit |
| `-n`, `--dry-run` | Run without saving state or sending Telegram messages |
| `--force` | Force a Telegram notification even if routine is unchanged |
| `-c`, `--config <path>` | Custom path to `config.json` |
| `--courses <path>` | Custom path to `courses.json` |
| `-f`, `--file <path>` | Parse a local `.xlsx` file instead of downloading from Google Sheets |

---

## GitHub Actions Setup

This repository includes a scheduled GitHub Action in `.github/workflows/check_routine.yml` that checks the sheet every 3 hours.

### 1. Add Repository Secrets

Navigate to **Settings > Secrets and variables > Actions** in your GitHub repository and add:

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from [@BotFather](https://t.me/BotFather).
- `TELEGRAM_CHAT_ID`: The target Telegram chat/group/channel ID (or comma-separated list of IDs).

### 2. Configure Workflow Permissions

Ensure the GitHub Action can persist state back to the repository:

1. Go to **Settings > Actions > General**.
2. Under **Workflow permissions**, select **Read and write permissions**.
3. Save changes.

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
  "fetch_failures_before_alert": 3,
  "heartbeat_days": 7
}
```

- `sheet_id`: Google Spreadsheet ID (from the sheet URL).
- `sheet_tab`: Target sheet tab name.
- `batch`: Target batch identifier (e.g. `71`).
- `fetch_failures_before_alert`: Consecutive download errors before sending an alert.
- `heartbeat_days`: Days between confirmation messages when the routine remains unchanged.

### `courses.json`

Maps 4-digit course numbers to course titles and expected weekly hours:

```json
{
  "1102": {"title": "Fundamentals of English", "credits": 3, "weekly_hours": 3},
  "1105": {"title": "Differential & Integral Calculus", "credits": 3, "weekly_hours": 3},
  "1112": {"title": "Physics", "credits": 2, "weekly_hours": 2},
  "1114": {"title": "Physics Sessional", "credits": 1, "weekly_hours": 2},
  "1123": {"title": "Introduction to Computer Science", "credits": 2, "weekly_hours": 2},
  "1124": {"title": "Basic Programming Lab (Python)", "credits": 1, "weekly_hours": 2}
}
```

---

## License

MIT
