"""MIU Routine Monitor & Telegram Notifier.

Monitors Google Sheets for routine changes, extracts batch sessions,
diffs against previous state, and alerts via Telegram.
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from .diff import diff_sessions, has_changes, render_changes, render_schedule, render_warnings
    from .grid import content_hash, load_grids
    from .routine import ParseError, parse_routine
    from .state import append_history, days_since, load as load_state, now_iso, save as save_state
    from .telegram import TelegramError, from_env, send as send_telegram
except ImportError:
    from diff import diff_sessions, has_changes, render_changes, render_schedule, render_warnings
    from grid import content_hash, load_grids
    from routine import ParseError, parse_routine
    from state import append_history, days_since, load as load_state, now_iso, save as save_state
    from telegram import TelegramError, from_env, send as send_telegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MIUroutine")


def fetch_sheet_bytes(sheet_id: str, timeout: int = 30) -> bytes:
    """Download Google Sheets spreadsheet as XLSX bytes."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; MIUroutine/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} when fetching spreadsheet")
        return resp.read()


def run(
    config_path: Path,
    courses_path: Path = None,
    local_file: Path = None,
    dry_run: bool = False,
    force_notify: bool = False,
    print_schedule_only: bool = False,
    force_daily_report: bool = False,
) -> int:
    # 1. Load config
    if not config_path.is_file():
        logger.error(f"Config file not found: {config_path}")
        return 1

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    base_dir = config_path.parent
    sheet_id = config.get("sheet_id")
    sheet_tab = config.get("sheet_tab")
    batch = str(config.get("batch", "")).strip()
    state_file = base_dir / config.get("state_file", f"state/batch{batch}.json")
    history_file = base_dir / config.get("history_file", "state/history.log")
    fetch_failures_before_alert = int(config.get("fetch_failures_before_alert", 3))
    heartbeat_days = float(config.get("heartbeat_days", 7))

    # 2. Load courses metadata
    courses = {}
    if courses_path is None:
        courses_path = base_dir / "courses.json"
    if courses_path.is_file():
        with open(courses_path, "r", encoding="utf-8") as f:
            courses = json.load(f)

    # 3. Load telegram settings
    tg_token, tg_chats, tg_base = None, [], "https://api.telegram.org"
    try:
        tg_token, tg_chats, tg_base = from_env()
    except TelegramError as e:
        if not dry_run and not print_schedule_only:
            logger.warning(f"Telegram not configured ({e}). Notifications will be logged only.")

    admin_chat_id = (
        os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
        or str(config.get("admin_chat_id", "")).strip()
        or (tg_chats[0] if tg_chats else "")
    )

    state = load_state(str(state_file))

    # Initialize 24-hour daily report stats
    stats = state.setdefault("stats_24h", {
        "checks": 0,
        "parses": 0,
        "changes": 0,
        "errors": 0,
        "window_start": now_iso(),
    })
    stats["checks"] = stats.get("checks", 0) + 1
    if not stats.get("window_start"):
        stats["window_start"] = now_iso()

    # 4. Fetch xlsx data
    xlsx_data = None
    if local_file:
        logger.info(f"Loading local spreadsheet file: {local_file}")
        with open(local_file, "rb") as f:
            xlsx_data = f.read()
    else:
        logger.info(f"Fetching routine from Google Sheets (ID: {sheet_id})...")
        try:
            xlsx_data = fetch_sheet_bytes(sheet_id)
            state["fetch_failures"] = 0
        except Exception as e:
            state["fetch_failures"] = state.get("fetch_failures", 0) + 1
            stats["errors"] = stats.get("errors", 0) + 1
            err_msg = f"Failed to fetch spreadsheet: {e}"
            logger.error(err_msg)
            append_history(str(history_file), f"FETCH_FAIL ({state['fetch_failures']}): {e}")

            if state["fetch_failures"] >= fetch_failures_before_alert:
                err_hash = hashlib.sha256(str(e).encode()).hexdigest()[:12]
                if tg_token and tg_chats and state.get("last_error_hash") != err_hash:
                    alert_text = (
                        f"⚠️ <b>MIU Routine Alert</b>\n"
                        f"Failed to fetch routine after {state['fetch_failures']} attempts.\n"
                        f"Error: {e}"
                    )
                    try:
                        send_telegram(alert_text, tg_token, tg_chats, tg_base)
                        state["last_error_hash"] = err_hash
                    except Exception as te:
                        logger.error(f"Failed to send Telegram failure alert: {te}")
            if not dry_run:
                save_state(str(state_file), state)
            return 1

    # 5. Parse grids
    try:
        grids = load_grids(xlsx_data)
    except Exception as e:
        stats["errors"] = stats.get("errors", 0) + 1
        logger.error(f"Failed to parse xlsx file: {e}")
        append_history(str(history_file), f"PARSE_ERROR: {e}")
        return 1

    curr_hash = content_hash(grids)

    # Find the target sheet
    target_grid = None
    if sheet_tab:
        target_grid = next((g for g in grids if g.name.strip().lower() == sheet_tab.strip().lower()), None)
    if not target_grid and grids:
        target_grid = grids[0]

    if not target_grid:
        stats["errors"] = stats.get("errors", 0) + 1
        logger.error(f"No valid sheet grid found (expected tab: {sheet_tab})")
        return 1

    # 6. Extract batch sessions
    try:
        parsed = parse_routine(target_grid, batch, courses)
        stats["parses"] = stats.get("parses", 0) + 1
    except ParseError as pe:
        stats["errors"] = stats.get("errors", 0) + 1
        logger.error(f"Routine parse error: {pe}")
        append_history(str(history_file), f"ROUTINE_PARSE_ERROR: {pe}")
        return 1

    if print_schedule_only:
        print(f"=== MIU Routine (Batch {batch}) ===")
        if parsed.updated_on:
            print(f"Sheet updated: {parsed.updated_on}")
        if parsed.warnings:
            print(render_warnings(parsed.warnings))
        print("\n" + render_schedule(parsed.sessions))
        return 0

    old_sessions = state.get("sessions", [])
    old_hash = state.get("content_hash", "")
    is_initial_run = not old_sessions and not old_hash

    diff = diff_sessions(old_sessions, parsed.sessions)
    changes_detected = has_changes(diff)

    logger.info(
        f"Extracted {len(parsed.sessions)} sessions. "
        f"Sheet update date: {parsed.updated_on or 'N/A'}. "
        f"Content hash: {curr_hash[:10]} (old: {old_hash[:10] if old_hash else 'none'})"
    )

    # 7. Check notifications
    message_to_send = None

    if is_initial_run or force_notify:
        logger.info("Initial run or forced notification requested.")
        title = "📅 <b>MIU Routine Initialized</b>" if is_initial_run else "📅 <b>Current MIU Routine</b>"
        body = [f"{title} (Batch {batch})"]
        if parsed.updated_on:
            body.append(f"Sheet updated on: <b>{parsed.updated_on}</b>")
        if parsed.warnings:
            body.append("\n" + render_warnings(parsed.warnings))
        body.append("\n" + render_schedule(parsed.sessions))
        message_to_send = "\n".join(body)
        log_entry = f"INITIAL_RUN: {len(parsed.sessions)} sessions loaded"
    elif curr_hash != old_hash:
        if changes_detected:
            stats["changes"] = stats.get("changes", 0) + 1
            logger.info(f"Changes detected for batch {batch}!")
            body = [f"🔔 <b>MIU Routine Update (Batch {batch})</b>"]
            if parsed.updated_on:
                body.append(f"Sheet updated on: <b>{parsed.updated_on}</b>")
            body.append("\n" + render_changes(diff))
            if parsed.warnings:
                body.append("\n" + render_warnings(parsed.warnings))
            body.append("\n<b>Full Updated Routine:</b>")
            body.append(render_schedule(parsed.sessions))
            message_to_send = "\n".join(body)
            log_entry = (
                f"CHANGED: added={len(diff['added'])}, "
                f"removed={len(diff['removed'])}, changed={len(diff['changed'])}"
            )
        else:
            logger.info("Sheet changed, but no session changes for our batch.")
            log_entry = "HASH_CHANGED: no changes for batch"
    else:
        # Check heartbeat
        last_notif = state.get("last_heartbeat") or state.get("last_checked")
        if days_since(last_notif) >= heartbeat_days:
            logger.info(f"Heartbeat interval ({heartbeat_days} days) reached.")
            msg = (
                f"💓 <b>MIU Routine Heartbeat</b>\n"
                f"Monitor is active. No changes detected for Batch {batch}.\n"
                f"Sheet last updated on: {parsed.updated_on or 'N/A'}"
            )
            message_to_send = msg
            state["last_heartbeat"] = now_iso()
            log_entry = "HEARTBEAT_SENT"
        else:
            logger.info("Routine is up to date. No changes detected.")
            log_entry = "NO_CHANGE"

    # Send telegram message if any
    if message_to_send:
        if dry_run:
            print("\n[DRY RUN] Would send Telegram notification:")
            print(message_to_send)
        elif tg_token and tg_chats:
            try:
                send_telegram(message_to_send, tg_token, tg_chats, tg_base)
                logger.info("Telegram notification sent successfully.")
            except Exception as te:
                logger.error(f"Failed to send Telegram notification: {te}")
                append_history(str(history_file), f"TELEGRAM_ERROR: {te}")

    # 8. Check 24-hour Daily Health Report to Admin
    window_start = stats.get("window_start")
    if not window_start:
        stats["window_start"] = now_iso()
        window_start = stats["window_start"]

    if admin_chat_id and (force_daily_report or days_since(window_start) >= 1.0):
        logger.info(f"Preparing 24h Daily Health Report for admin ({admin_chat_id})...")
        err_count = stats.get("errors", 0)
        status_icon = "Healthy & Operational 🟢" if err_count == 0 else f"Errors Encountered ({err_count}) ⚠️"
        report_msg = (
            f"📊 <b>MIU Routine Monitor — Daily Health Report</b>\n\n"
            f"• <b>Checks executed (last 24h):</b> {stats.get('checks', 0)}\n"
            f"• <b>Successful routine parses:</b> {stats.get('parses', 0)}\n"
            f"• <b>Routine changes broadcasted:</b> {stats.get('changes', 0)}\n"
            f"• <b>Errors encountered:</b> {err_count}\n"
            f"• <b>Spreadsheet updated on:</b> <b>{parsed.updated_on or 'N/A'}</b>\n"
            f"• <b>Status:</b> {status_icon}"
        )
        if dry_run:
            print("\n[DRY RUN] Would send 24h Daily Health Report to admin:")
            print(report_msg)
        elif tg_token:
            try:
                send_telegram(report_msg, tg_token, [admin_chat_id], tg_base)
                logger.info("Daily health report sent to admin.")
                append_history(str(history_file), "DAILY_HEALTH_REPORT_SENT")
            except Exception as te:
                logger.error(f"Failed to send daily health report to admin: {te}")

        # Reset daily window
        stats["checks"] = 0
        stats["parses"] = 0
        stats["changes"] = 0
        stats["errors"] = 0
        stats["window_start"] = now_iso()

    # 9. Update and save state
    if not dry_run:
        state["content_hash"] = curr_hash
        state["sessions"] = parsed.sessions
        state["warnings"] = parsed.warnings
        state["sheet_updated_on"] = parsed.updated_on
        state["last_checked"] = now_iso()
        state["fetch_failures"] = 0
        state["last_error_hash"] = ""
        save_state(str(state_file), state)
        append_history(str(history_file), log_entry)

    logger.info("Run finished successfully.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="MIU Routine Monitor & Telegram Notifier")
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.json"),
        help="Path to config.json file (default: config.json)",
    )
    parser.add_argument(
        "--courses",
        type=Path,
        default=None,
        help="Path to courses.json file (default: courses.json in config directory)",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        default=None,
        help="Path to local .xlsx file instead of downloading from Google Sheets",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Run without saving state or sending Telegram messages",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force notification even if routine is unchanged",
    )
    parser.add_argument(
        "--print-schedule",
        "-p",
        action="store_true",
        help="Print the current schedule to stdout and exit",
    )
    parser.add_argument(
        "--daily-report",
        action="store_true",
        help="Force send the 24-hour daily health report to admin",
    )

    args = parser.parse_args()

    # If running from outside root, search relative to package or current dir
    config_path = args.config
    if not config_path.is_file():
        repo_config = Path(__file__).parent / "config.json"
        if repo_config.is_file():
            config_path = repo_config

    return run(
        config_path=config_path,
        courses_path=args.courses,
        local_file=args.file,
        dry_run=args.dry_run,
        force_notify=args.force,
        print_schedule_only=args.print_schedule,
        force_daily_report=args.daily_report,
    )


if __name__ == "__main__":
    sys.exit(main())
