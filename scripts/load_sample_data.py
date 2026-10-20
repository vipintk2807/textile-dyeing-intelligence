"""Load (or remove) SYNTHETIC demonstration data. Never runs automatically.

Usage:
  python scripts/load_sample_data.py --db demo.db            load into a demo database
  python scripts/load_sample_data.py --remove                remove only SYN- records
Loading into a database that already holds real records is refused unless
--allow-non-empty is given.
"""

import argparse
import sys

import bootstrap  # noqa: F401  # isort: skip

from textile_dyeing_intelligence import sample_data
from textile_dyeing_intelligence.config import resolve_db_path
from textile_dyeing_intelligence.database import connect, initialize_database
from textile_dyeing_intelligence.errors import TDIError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--db", help="database file (default: per-user data folder or TDI_DB_PATH)")
    parser.add_argument("--remove", action="store_true", help="remove SYN- sample records only")
    parser.add_argument("--allow-non-empty", action="store_true", help="load even if non-sample records exist")
    args = parser.parse_args()
    path = resolve_db_path(args.db)
    try:
        initialize_database(path)
        conn = connect(path)
        try:
            if args.remove:
                print(f"Removed {sample_data.remove_sample_data(conn)} synthetic batches from {path}")
                return 0
            if sample_data.has_non_sample_records(conn) and not args.allow_non_empty:
                print(
                    "Refused: this database already contains non-sample records.\n"
                    "Use a separate demo database (--db demo.db) or pass --allow-non-empty."
                )
                return 2
            counts = sample_data.load_sample_data(conn)
        finally:
            conn.close()
    except TDIError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Loaded SYNTHETIC sample data into {path}")
    for table, n in counts.items():
        print(f"  {table}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
