"""CSV export with spreadsheet formula-injection protection.

Policy: any *text* cell whose first non-whitespace character is ``=``, ``+``, ``-`` or ``@``
(or that starts with a tab or carriage return) is prefixed with a single quote so common
spreadsheet programs show it as text. Numeric cells (``int``/``Decimal``) are written as
numbers and never altered. The database is never modified. Files are UTF-8 with a byte-order
mark so Excel on Windows reads non-ASCII text correctly. Missing values are written as an
empty cell; calculations that cannot be performed are written as ``Unavailable``.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

_FORMULA_RE = re.compile(r"^[\s\x00-\x1f\x7f]*[=+\-@]")


def safe_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    text = str(value)
    if _FORMULA_RE.match(text) or text[:1] in ("\t", "\r"):
        return "'" + text
    return text


def rows_to_csv(columns: Sequence[str], rows: Sequence[dict[str, Any]]) -> bytes:
    """Serialise rows with a stable column order. An empty result yields a header-only file."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([safe_cell(col) for col in columns])
    for row in rows:
        writer.writerow([safe_cell(row.get(col)) for col in columns])
    return buffer.getvalue().encode("utf-8-sig")


def export_filename(stub: str, start_date: str | None = None, end_date: str | None = None) -> str:
    parts = [stub]
    if start_date or end_date:
        parts.append(f"{start_date or 'start'}_to_{end_date or 'end'}")
    return "_".join(parts) + ".csv"
