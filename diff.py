"""Compare two session lists and render Telegram-ready (HTML) text."""
from html import escape

from .routine import DAY_ORDER, _day_key


def _key(s):
    return (s["day"], s["start"], s["end"], s["code"], s["teacher"], s["room"])


def diff_sessions(old, new):
    """Returns {'added': [...], 'removed': [...], 'changed': [(old, new), ...]}.

    A removed and an added session of the same course are paired as 'changed'
    (e.g. a class that moved to another day or room).
    """
    old_keys, new_keys = {_key(s) for s in old}, {_key(s) for s in new}
    removed = sorted((s for s in old if _key(s) not in new_keys), key=_day_key)
    added = sorted((s for s in new if _key(s) not in old_keys), key=_day_key)
    changed = []
    for r in list(removed):
        match = next((a for a in added if a["code"] == r["code"]), None)
        if match:
            changed.append((r, match))
            removed.remove(r)
            added.remove(match)
    return {"added": added, "removed": removed, "changed": changed}


def has_changes(d) -> bool:
    return bool(d["added"] or d["removed"] or d["changed"])


def _t(m):
    h, mm = divmod(m, 60)
    return f"{h % 12 or 12}:{mm:02d}", "AM" if h < 12 else "PM"


def fmt_range(start, end) -> str:
    (a, ap1), (b, ap2) = _t(start), _t(end)
    return f"{a}–{b} {ap1}" if ap1 == ap2 else f"{a} {ap1}–{b} {ap2}"


def _course(s) -> str:
    return f"{s['title']} ({s['code']})" if s["title"] != s["code"] else s["code"]


def _line(s, with_day=False) -> str:
    day = f"{s['day']} · " if with_day else ""
    return f"{day}{fmt_range(s['start'], s['end'])} · {escape(_course(s))} · {escape(s['teacher'])} · {escape(s['room'])}"


def render_schedule(sessions) -> str:
    out, last = [], None
    for s in sorted(sessions, key=_day_key):
        if s["day"] != last:
            out.append(f"\n<b>{escape(s['day'])}</b>")
            last = s["day"]
        out.append("• " + _line(s))
    return "\n".join(out).strip()


def render_changes(d) -> str:
    out = []
    if d["changed"]:
        out.append("<b>Changed</b>")
        for old, new in d["changed"]:
            out.append(f"• {escape(_course(new))}\n   was: {_line(old, True)}\n   now: {_line(new, True)}")
    if d["added"]:
        out.append("<b>Added</b>")
        out += [f"• {_line(s, True)}" for s in d["added"]]
    if d["removed"]:
        out.append("<b>Removed</b>")
        out += [f"• {_line(s, True)}" for s in d["removed"]]
    return "\n".join(out)


def render_warnings(warnings) -> str:
    return "\n".join(f"⚠️ {escape(w)}" for w in warnings)
