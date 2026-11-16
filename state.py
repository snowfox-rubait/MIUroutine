import json
import os
from datetime import datetime, timezone

DEFAULT = {
    "content_hash": "",
    "sessions": [],
    "warnings": [],
    "sheet_updated_on": "",
    "last_error_hash": "",
    "fetch_failures": 0,
    "last_checked": "",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return {**DEFAULT, **json.load(f)}
    except FileNotFoundError:
        return dict(DEFAULT)


def save(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)  # atomic: a crash can't leave a half-written state file


def append_history(path: str, line: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{now_iso()}  {line}\n")


def days_since(iso: str) -> float:
    if not iso:
        return 1e9
    then = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400
