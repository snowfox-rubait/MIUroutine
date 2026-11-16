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
