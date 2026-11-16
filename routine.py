"""Extract one batch's sessions from the routine grid.

Nothing here depends on fixed cell addresses: the header row, day column,
room column, time columns, teacher legend and "Updated on" line are all found
by their content, so inserting rows/columns in the sheet doesn't break it.
"""
import re
from dataclasses import dataclass, field

DAY_NAMES = {
    "SAT": "Saturday", "SUN": "Sunday", "MON": "Monday", "TUE": "Tuesday",
    "WED": "Wednesday", "THU": "Thursday", "FRI": "Friday",
}
DAY_ORDER = list(DAY_NAMES.values())

TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})$")
COURSE_RE = re.compile(r"([A-Za-z]{2,4})\s*(\d{4})")
HEADER_SEARCH_ROWS = 60
BLANK_ROWS_END_TABLE = 3


class ParseError(Exception):
    pass


@dataclass
class ParseResult:
    sessions: list = field(default_factory=list)  # list of dicts, sorted
    warnings: list = field(default_factory=list)
    updated_on: str = ""


def _minutes(h: int, m: int) -> int:
    # Headers have no AM/PM ("1:00-2:00" means 13:00). University hours run
    # roughly 8:00-18:00, so hours below 8 are afternoon.
    return (h + 12 if h < 8 else h) * 60 + m


def _find_header(g):
    for r in range(1, min(g.max_row, HEADER_SEARCH_ROWS) + 1):
        day_col = room_col = None
        times = {}
        for c in range(1, g.max_col + 1):
            v = g.get(r, c)
            low = v.lower()
            if low == "day":
                day_col = c
            elif low == "room":
                room_col = c
            else:
                m = TIME_RE.match(v)
                if m:
                    times[c] = (_minutes(int(m[1]), int(m[2])), _minutes(int(m[3]), int(m[4])))
        if day_col and room_col and times:
            return r, day_col, room_col, times
    return None


def _teacher_legend(g):
    """abbreviation -> full name, from the 'Abbreviation | Teacher's Name' table."""
    for (r, c), v in sorted(g.values.items()):
        if v.lower().startswith("abbreviation"):
            name_col = next((cc for cc in range(1, g.max_col + 1)
                             if "name" in g.get(r, cc).lower()), None)
            if not name_col:
                return {}
            legend, blanks = {}, 0
            for rr in range(r + 1, g.max_row + 1):
                abbr, name = g.get(rr, c), g.get(rr, name_col)
                if abbr and name:
                    legend[abbr.upper()] = name
                    blanks = 0
                else:
                    blanks += 1
                    if blanks >= BLANK_ROWS_END_TABLE:
                        break
            return legend
    return {}


def _updated_on(g) -> str:
    for r in range(1, min(g.max_row, 15) + 1):
        for c in range(1, g.max_col + 1):
            m = re.search(r"updated on:?\s*(.+)", g.get(r, c), re.I)
            if m:
                return m[1].strip()
    return ""


def _mentions_batch(text, batch) -> bool:
    return re.search(rf"(?<!\d){re.escape(batch)}(?!\d)", text) is not None


def _batch_matches(spec, batch) -> bool:
    spec = spec.strip()
    return _mentions_batch(spec, batch)


def _day_key(s: dict):
    day_idx = DAY_ORDER.index(s["day"]) if s.get("day") in DAY_ORDER else 99
    return (day_idx, s.get("start", 0), s.get("end", 0), s.get("code", ""))


def parse_routine(g, batch: str, courses: dict = None) -> ParseResult:
    """Extract sessions for `batch` from Grid `g`.

    courses: dict mapping 4-digit course number -> metadata (title, expected weekly_hours, etc.)
    """
    if courses is None:
        courses = {}

    header = _find_header(g)
    if not header:
        raise ParseError(f"Could not find schedule table header in sheet {g.name!r}")

    header_row, day_col, room_col, times = header
    legend = _teacher_legend(g)
    updated_on = _updated_on(g)

    sessions = []
    warnings = []
    current_day = None

    for r in range(header_row + 1, g.max_row + 1):
        day_val = g.get(r, day_col).strip()
        if day_val:
            up = day_val.upper()
            if up in DAY_NAMES:
                current_day = DAY_NAMES[up]
            elif up in DAY_ORDER:
                current_day = up

        # Check if we have reached the end of the schedule (e.g. teacher legend or signature)
        row_text = " ".join(g.get(r, c) for c in range(1, g.max_col + 1)).lower()
        if "abbreviation" in row_text and "teacher" in row_text:
            break

        room = g.get(r, room_col).strip()
        if not room or not current_day:
            continue

        for c in sorted(times.keys()):
            val = g.get(r, c).strip()
            if not val or not _mentions_batch(val, batch):
                continue

            span_r, span_c = g.span(r, c)
            start_min = times[c][0]
            end_col = c + span_c - 1
            if end_col in times:
                end_min = times[end_col][1]
            else:
                end_min = times[c][1] + 60 * (span_c - 1)

            parts = [p.strip() for p in val.split("/") if p.strip()]
            if len(parts) >= 3:
                batch_spec = parts[0]
                teacher_abbr = parts[-1]
                course_str = "".join(parts[1:-1])
            elif len(parts) == 2:
                batch_spec = parts[0]
                teacher_abbr = ""
                course_str = parts[1]
            else:
                batch_spec = val
                teacher_abbr = ""
                course_str = val

            if not _batch_matches(batch_spec, batch):
                continue

            cm = COURSE_RE.search(course_str)
            if cm:
                dept, num = cm.group(1).upper(), cm.group(2)
                code = f"{dept}{num}"
            else:
                num = ""
                code = re.sub(r"\s+", "", course_str)

            cinfo = courses.get(num, {}) if num else {}
            title = cinfo.get("title", code)
            teacher = legend.get(teacher_abbr.upper(), teacher_abbr) if teacher_abbr else "TBA"

            sessions.append({
                "day": current_day,
                "start": start_min,
                "end": end_min,
                "code": code,
                "title": title,
                "teacher": teacher,
                "room": room,
            })

    sessions.sort(key=_day_key)

    # Validate against expected weekly hours from courses config
    if courses:
        hours_by_num = {}
        for s in sessions:
            m = COURSE_RE.search(s["code"])
            num = m.group(2) if m else s["code"]
            duration = (s["end"] - s["start"]) / 60
            hours_by_num[num] = hours_by_num.get(num, 0) + duration

        for num, cinfo in courses.items():
            if num.startswith("_"):
                continue
            expected = cinfo.get("weekly_hours")
            if expected is not None:
                actual = hours_by_num.get(num, 0)
                if abs(actual - expected) > 0.01:
                    title = cinfo.get("title", num)
                    warnings.append(
                        f"{title} ({num}): expected {expected}h/week, found {int(actual) if actual.is_integer() else actual}h"
                    )

    return ParseResult(sessions=sessions, warnings=warnings, updated_on=updated_on)
