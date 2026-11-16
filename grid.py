"""Load an .xlsx into a plain Grid (values + merged-cell spans) and hash its content."""
import hashlib
import io
import json
import re
from dataclasses import dataclass, field

import openpyxl


def clean(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


@dataclass
class Grid:
    name: str
    values: dict = field(default_factory=dict)  # (row, col) -> text, merged ranges only at their top-left cell
    spans: dict = field(default_factory=dict)   # (row, col) -> (n_rows, n_cols)
    max_row: int = 0
    max_col: int = 0

    def get(self, r, c) -> str:
        return self.values.get((r, c), "")

    def span(self, r, c):
        return self.spans.get((r, c), (1, 1))

    def row_has_values(self, r) -> bool:
        return any(self.values.get((r, c)) for c in range(1, self.max_col + 1))


def load_grids(data: bytes) -> list:
    """Parse xlsx bytes into one Grid per sheet. Raises on corrupt files."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    grids = []
    for ws in wb.worksheets:
        g = Grid(name=ws.title)
        for row in ws.iter_rows():
            for cell in row:
                text = clean(cell.value)
                if text:
                    g.values[(cell.row, cell.column)] = text
                    g.max_row = max(g.max_row, cell.row)
                    g.max_col = max(g.max_col, cell.column)
        for m in ws.merged_cells.ranges:
            g.spans[(m.min_row, m.min_col)] = (m.max_row - m.min_row + 1, m.max_col - m.min_col + 1)
        grids.append(g)
    return grids


def content_hash(grids) -> str:
    """Hash of what the sheet *says*, not of the file bytes.

    Google's xlsx export embeds timestamps etc., so the raw file hash would
    differ on every download. Cell text + merges are stable.
    """
    h = hashlib.sha256()
    for g in grids:
        h.update(g.name.encode())
        h.update(json.dumps(sorted((list(k), v) for k, v in g.values.items())).encode())
        h.update(json.dumps(sorted((list(k), list(v)) for k, v in g.spans.items() if v != (1, 1))).encode())
    return h.hexdigest()
