"""Local configuration and database-path resolution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Textile Dyeing Intelligence"
APP_DIR_NAME = "TextileDyeingIntelligence"
DB_FILENAME = "textile_dyeing.db"
ENV_DB_PATH = "TDI_DB_PATH"

MISSING_LABEL = "Not recorded"
UNAVAILABLE_LABEL = "Unavailable"

#: Maximum digits accepted for quantities (see docs in README, "Numbers and units").
MAX_INTEGER_DIGITS = 15
MAX_DECIMAL_PLACES = 6

#: Maximum rows shown in on-screen tables before the user is asked to narrow filters.
TABLE_ROW_LIMIT = 500


def default_data_dir() -> Path:
    """Per-user writable data directory (not the current working directory)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "textile-dyeing-intelligence"


def resolve_db_path(override: str | os.PathLike[str] | None = None) -> Path:
    """Return the SQLite database path.

    Order of precedence: explicit ``override`` argument, the ``TDI_DB_PATH`` environment
    variable, then ``<per-user data dir>/textile_dyeing.db``.
    """
    if override:
        return Path(override).expanduser().resolve()
    env_value = os.environ.get(ENV_DB_PATH)
    if env_value:
        return Path(env_value).expanduser().resolve()
    return default_data_dir() / DB_FILENAME
