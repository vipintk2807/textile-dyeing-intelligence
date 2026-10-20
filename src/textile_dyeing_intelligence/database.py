"""SQLite connections, transactions, migrations, backup and restore."""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path

from . import timeutil
from .errors import Conflict, StorageError, ValidationFailure
from .schema import EXPECTED_TABLES, LATEST_VERSION, MIGRATIONS

logger = logging.getLogger("textile_dyeing_intelligence")

_UNIQUE_MESSAGES = {
    "batches.batch_code": "A batch with this identifier already exists. Enter a unique identifier.",
    "machines.machine_code": "A machine with this identifier already exists. Enter a unique identifier.",
    "recipes.recipe_code": "A recipe with this identifier already exists. Enter a unique identifier.",
    "recipe_revisions.": "This recipe already has a revision with that identifier. Enter a new revision identifier.",
    "chemical_materials.": "A material with this name already exists.",
    "quality_inspections.inspection_code": "An inspection with this identifier already exists.",
    "quality_inspections.batch_id": "An inspection of this type was already recorded for this batch "
    "at the same date and time. Nothing was saved again.",
    "ux_process_duplicate": "An identical process record already exists for this batch "
    "(same parameter, value, unit and observation time). Nothing was saved again.",
    "consumption_records.": "An identical consumption record already exists for this batch "
    "(same material, category, quantity, unit, basis and time). Nothing was saved again.",
    "rework_records.rework_code": "A rework record with this identifier already exists.",
}


def map_integrity_error(exc: sqlite3.IntegrityError) -> Exception:
    """Translate a constraint failure into a user-safe application error."""
    text = str(exc)
    if text.startswith("TDI: "):
        return Conflict(text[5:])
    if "UNIQUE constraint failed" in text:
        for needle, message in _UNIQUE_MESSAGES.items():
            if needle in text:
                return Conflict(message)
        return Conflict("A record with the same identifier already exists.")
    if "FOREIGN KEY constraint failed" in text:
        return ValidationFailure(
            "A referenced record does not exist, or this record is still referenced by "
            "other records. Select a valid record, or archive it instead of deleting it."
        )
    if "CHECK constraint failed" in text or "NOT NULL constraint failed" in text:
        return ValidationFailure(
            "The entered values break a database rule. Check required fields, quantities and dates, then try again."
        )
    logger.exception("Unmapped integrity error: %s", text)
    return StorageError()


def connect(db_path: str | os.PathLike[str], *, create: bool = True) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced.

    The connection is in autocommit mode (``isolation_level=None``); use
    :func:`transaction` for every write.
    """
    path = Path(db_path)
    try:
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        elif not path.exists():
            raise StorageError("The database file was not found.")
        conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            conn.close()
            raise StorageError("Foreign-key enforcement could not be enabled.")
    except (sqlite3.Error, OSError) as exc:
        logger.exception("Could not open database %s", path)
        raise StorageError(
            "The database could not be opened. Check that the folder exists, is writable and "
            "that the file is a valid database."
        ) from exc
    return conn


@contextmanager
def open_connection(db_path: str | os.PathLike[str]) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def _rollback(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        with suppress(sqlite3.Error):
            conn.execute("ROLLBACK")


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block atomically.

    Commits when the block finishes, rolls back on any exception. Constraint failures are
    translated to ``Conflict`` / ``ValidationFailure``; other database errors become
    ``StorageError``. A nested call joins the outer transaction.
    """
    if conn.in_transaction:
        yield conn
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.Error as exc:
        logger.exception("BEGIN failed")
        raise StorageError() from exc
    try:
        yield conn
    except sqlite3.IntegrityError as exc:
        _rollback(conn)
        raise map_integrity_error(exc) from exc
    except sqlite3.Error as exc:
        _rollback(conn)
        logger.exception("Database error inside transaction")
        raise StorageError() from exc
    except BaseException:
        _rollback(conn)
        raise
    else:
        try:
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            _rollback(conn)
            logger.exception("COMMIT failed")
            raise StorageError() from exc


# --- Initialisation and migrations ------------------------------------------------------


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def apply_migrations(
    conn: sqlite3.Connection,
    migrations: Sequence[tuple[int, str]] = MIGRATIONS,
) -> int:
    """Apply pending migrations, each atomically with its version bump."""
    current = schema_version(conn)
    latest = max((v for v, _ in migrations), default=0)
    if current > latest:
        raise StorageError(
            "This database was created by a newer version of the application. Update the application before opening it."
        )
    for version, sql in sorted(migrations):
        if version <= current:
            continue
        script = f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {int(version)};\nCOMMIT;"
        try:
            conn.executescript(script)
        except sqlite3.Error as exc:
            _rollback(conn)
            logger.exception("Migration %s failed", version)
            raise StorageError(
                f"The database could not be upgraded to schema version {version}. No partial changes were kept."
            ) from exc
        current = version
    return current


def initialize_database(
    db_path: str | os.PathLike[str],
    migrations: Sequence[tuple[int, str]] = MIGRATIONS,
) -> int:
    """Create or upgrade the database. Safe to run repeatedly; never deletes records."""
    conn = connect(db_path)
    try:
        version = apply_migrations(conn, migrations)
        conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()  # access check
        return version
    except sqlite3.DatabaseError as exc:
        logger.exception("Database file is unusable: %s", db_path)
        raise StorageError(
            "The database file could not be read. It may be damaged or not a database. "
            "Restore a backup or choose another database file."
        ) from exc
    finally:
        conn.close()


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows}


def integrity_problems(conn: sqlite3.Connection) -> list[str]:
    """Return a list of integrity problems (empty when the database is sound)."""
    problems: list[str] = []
    result = conn.execute("PRAGMA integrity_check").fetchall()
    if [r[0] for r in result] != ["ok"]:
        problems.extend(str(r[0]) for r in result)
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    problems.extend(f"foreign key violation in {r[0]} (rowid {r[1]})" for r in violations)
    return problems


# --- Backup and restore ------------------------------------------------------------------


def backup_database(
    db_path: str | os.PathLike[str],
    backup_path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> Path:
    """Create a consistent copy using SQLite's online backup API.

    Safe to run while the application is open, because SQLite takes a consistent snapshot.
    """
    src = Path(db_path)
    dest = Path(backup_path)
    if not src.exists():
        raise StorageError("The database file to back up was not found.")
    if src.resolve() == dest.resolve():
        raise StorageError("The backup file must be different from the database file.")
    if dest.exists() and not overwrite:
        raise StorageError("The backup file already exists. Choose a new file name.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.unlink(missing_ok=True)
    source = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
    target = sqlite3.connect(str(tmp))
    try:
        source.backup(target)
    except sqlite3.Error as exc:
        logger.exception("Backup failed")
        raise StorageError("The backup could not be created.") from exc
    finally:
        target.close()
        source.close()
    os.replace(tmp, dest)
    return dest


def validate_backup_file(path: str | os.PathLike[str]) -> None:
    """Raise ``StorageError`` unless ``path`` is a sound database of a supported version."""
    p = Path(path)
    if not p.is_file():
        raise StorageError("The backup file was not found.")
    try:
        conn = sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise StorageError("The backup file could not be opened.") from exc
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            result = [r[0] for r in conn.execute("PRAGMA integrity_check")]
            fk_problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        except sqlite3.DatabaseError as exc:
            raise StorageError("The file is not a valid database backup.") from exc
        if not set(EXPECTED_TABLES) <= tables:
            raise StorageError("The file is not a Textile Dyeing Intelligence database.")
        if version > LATEST_VERSION:
            raise StorageError("The backup was created by a newer version of the application.")
        if result != ["ok"] or fk_problems:
            raise StorageError("The backup file failed its integrity check and was not used.")
    finally:
        conn.close()


def restore_database(
    backup_path: str | os.PathLike[str],
    db_path: str | os.PathLike[str],
) -> Path | None:
    """Replace ``db_path`` with the contents of ``backup_path``.

    Close the application first. An existing database is copied to a timestamped
    ``.pre-restore`` file before it is replaced; that path is returned (or ``None`` when
    there was no previous database).
    """
    validate_backup_file(backup_path)
    dest = Path(db_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    safety_copy: Path | None = None
    if dest.exists():
        stamp = timeutil.now().strftime("%Y%m%d-%H%M%S")
        safety_copy = dest.with_name(f"{dest.name}.pre-restore-{stamp}")
        backup_database(dest, safety_copy)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), suffix=".restore.tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copyfile(backup_path, tmp)
        validate_backup_file(tmp)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return safety_copy
