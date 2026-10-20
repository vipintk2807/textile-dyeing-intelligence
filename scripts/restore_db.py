"""Restore a backup. CLOSE the application first.

Usage:  python scripts/restore_db.py BACKUP_FILE [--db PATH]
The current database (if any) is first saved as <name>.pre-restore-<timestamp>.
"""

import argparse
import sys

import bootstrap  # noqa: F401  # isort: skip

from textile_dyeing_intelligence.config import resolve_db_path
from textile_dyeing_intelligence.database import restore_database
from textile_dyeing_intelligence.errors import TDIError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup")
    parser.add_argument("--db")
    args = parser.parse_args()
    db = resolve_db_path(args.db)
    try:
        safety = restore_database(args.backup, db)
    except TDIError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Restored {args.backup} -> {db}")
    if safety:
        print(f"Previous database kept as: {safety}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
