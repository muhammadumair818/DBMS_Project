"""Database layer for the Student Management System (SQLite, one file per department)."""
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime

DB_DIR = "."                 # where department .db files live
BACKUP_DIR = "backups"       # automatic safety copies are stored here
DEFAULT_DB = "central_system"

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no       TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    father_name   TEXT,
    email         TEXT,
    phone         TEXT,
    address       TEXT,
    fee_submitted INTEGER NOT NULL DEFAULT 0,
    gpa           REAL,
    photo         BLOB,
    deleted_at    TEXT
);
"""

# Columns added to databases created by earlier versions of the app (data is preserved)
_UPGRADE_COLUMNS = {
    "father_name": "TEXT",
    "email": "TEXT",
    "phone": "TEXT",
    "address": "TEXT",
    "fee_submitted": "INTEGER NOT NULL DEFAULT 0",
    "gpa": "REAL",
    "photo": "BLOB",
    "deleted_at": "TEXT",
}


def sanitize_name(name):
    """Keep only letters, digits and underscores; prefix '_' if it starts with a digit."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "", (name or "").strip())
    if cleaned and cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


def db_path(db_name):
    return os.path.join(DB_DIR, f"{db_name}.db")


def get_connection(db_name=None):
    conn = sqlite3.connect(db_path(db_name or DEFAULT_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session(db_name=None):
    """Commit on success, roll back on error, always close the connection."""
    conn = get_connection(db_name)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_name):
    """Create / upgrade the students table. Existing data is never deleted."""
    with db_session(db_name) as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(students)")]
        if cols and "roll_no" not in cols:  # unrelated old table with the same name -> keep it aside
            existing = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            n = 1
            while f"students_legacy{n}" in existing:
                n += 1
            conn.execute(f'ALTER TABLE "students" RENAME TO "students_legacy{n}"')
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(students)")}
        for col, ddl in _UPGRADE_COLUMNS.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE students ADD COLUMN {col} {ddl}")


# ------------------------------------------------------------- departments
def list_departments():
    names = [f[:-3] for f in os.listdir(DB_DIR) if f.endswith(".db")]
    return sorted(n for n in names if n != DEFAULT_DB)


def create_department(raw_name):
    """Returns (name, None) on success or (None, error_message)."""
    name = sanitize_name(raw_name)
    if not name:
        return None, "Enter a name using letters, numbers or underscore."
    if name.lower() == DEFAULT_DB:
        return None, f"'{DEFAULT_DB}' is reserved."
    if name.lower() in (d.lower() for d in list_departments()):
        return None, f"Department '{name}' already exists."
    init_schema(name)
    return name, None


def delete_department(name):
    if name not in list_departments():
        raise FileNotFoundError(f"Department '{name}' not found.")
    os.remove(db_path(name))


# ------------------------------------------------------------ backup / restore
def export_backup(db_name):
    """Return a consistent copy of the department database as bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "backup.db")
        src, dst = get_connection(db_name), sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        with open(target, "rb") as f:
            return f.read()


def inspect_backup(data):
    """Validate an uploaded backup. Returns (student_count, None) or (None, error)."""
    if not data.startswith(b"SQLite format 3\x00"):
        return None, "This is not a valid backup file."
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "check.db")
        with open(path, "wb") as f:
            f.write(data)
        try:
            conn = sqlite3.connect(path)
            try:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    return None, "The backup file appears to be damaged."
                cols = [r[1] for r in conn.execute("PRAGMA table_info(students)")]
                if "roll_no" not in cols:
                    return None, "This file does not contain student records."
                query = "SELECT COUNT(*) FROM students"
                if "deleted_at" in cols:
                    query += " WHERE deleted_at IS NULL"
                return conn.execute(query).fetchone()[0], None
            finally:
                conn.close()
        except sqlite3.Error as e:
            return None, f"Could not read the file: {e}"


def restore_backup(db_name, data):
    """Replace the department data with a backup. A safety copy of the current
    data is saved automatically in the backups/ folder first."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(BACKUP_DIR, f"{db_name}_before_restore_{stamp}.db"), "wb") as f:
        f.write(export_backup(db_name))
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "restore.db")
        with open(path, "wb") as f:
            f.write(data)
        src, dst = sqlite3.connect(path), sqlite3.connect(db_path(db_name))
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
    init_schema(db_name)
