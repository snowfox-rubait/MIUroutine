"""Minimal Telegram Bot API client (stdlib only)."""
import json
import os
import time
import urllib.error
import urllib.request

LIMIT = 4000  # Telegram's hard limit is 4096 characters per message


class TelegramError(Exception):
    pass


def chunk(text: str, limit: int = LIMIT):
    """Split on line boundaries so no message exceeds the limit."""
    parts, cur = [], ""
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts


def send(text: str, token: str, chat_ids: list, api_base: str = "https://api.telegram.org"):
    for chat_id in chat_ids:
        for part in chunk(text):
            _post(token, chat_id, part, api_base)


def _post(token, chat_id, text, api_base, attempts=3):
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"{api_base}/bot{token}/sendMessage", data=body,
                                 headers={"Content-Type": "application/json"})
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                if json.load(r).get("ok"):
                    return
                last = "Telegram replied ok=false"
        except urllib.error.HTTPError as e:
            # 4xx (bad token / chat id / bad HTML) will not fix itself by retrying
            detail = e.read().decode(errors="replace")[:300]
            last = f"HTTP {e.code}: {detail}"
            if e.code != 429 and 400 <= e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError) as e:
            last = f"network error: {e}"
        time.sleep(2 * (i + 1))
    # never include the token in the error text
    raise TelegramError(f"Could not send Telegram message ({last})".replace(token, "***"))


def from_env():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    if not token or not chats:
        raise TelegramError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set "
                            "(repo Settings > Secrets and variables > Actions).")
    return token, chats, os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org")
