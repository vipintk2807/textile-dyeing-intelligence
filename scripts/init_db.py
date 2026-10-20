"""Create or upgrade the database. Safe to run repeatedly; never deletes records.

Usage:  python scripts/init_db.py [--db PATH]
"""

import argparse
import sys

import bootstrap  # noqa: F401  (adds ./src to sys.path)  # isort: skip

from textile_dyeing_intelligence.config import resolve_db_path
from textile_dyeing_intelligence.database import initialize_database
from textile_dyeing_intelligence.errors import TDIError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="database file (default: per-user data folder or TDI_DB_PATH)")
    args = parser.parse_args()
    path = resolve_db_path(args.db)
    try:
        version = initialize_database(path)
    except TDIError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Database ready (schema version {version}): {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
