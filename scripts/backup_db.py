"""Create a consistent backup using SQLite's backup API (safe while the app is open).

Usage:  python scripts/backup_db.py [--db PATH] [--out BACKUP_FILE]
"""

import argparse
import sys
from datetime import datetime

import bootstrap  # noqa: F401  # isort: skip

from pathlib import Path

from textile_dyeing_intelligence.config import resolve_db_path
from textile_dyeing_intelligence.database import backup_database, validate_backup_file
from textile_dyeing_intelligence.errors import TDIError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--out", help="backup file (default: <db folder>/backups/<name>-<timestamp>.db)")
    args = parser.parse_args()
    db = resolve_db_path(args.db)
    out = Path(args.out) if args.out else (db.parent / "backups" / f"{db.stem}-{datetime.now():%Y%m%d-%H%M%S}.db")
    try:
        backup_database(db, out)
        validate_backup_file(out)
    except TDIError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Backup created and verified: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
