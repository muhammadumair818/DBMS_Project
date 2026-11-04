"""Database helpers for the Student Management System (SQLite)."""
import os
import re
import sqlite3
from contextlib import contextmanager

# Folder where department .db files live ("." = project folder)
DB_DIR = "."
DEFAULT_DB = "central_system"
SQLITE_TYPES = ["TEXT", "INTEGER", "REAL"]

# Core tables of the student system (protected from the generic "Advanced Tools")
SYSTEM_TABLES = {"students", "courses", "enrollments", "attendance", "results", "fees"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no        TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    father_name    TEXT,
    gender         TEXT DEFAULT 'Male',
    dob            TEXT,
    phone          TEXT,
    email          TEXT,
    address        TEXT,
    admission_date TEXT,
    status         TEXT NOT NULL DEFAULT 'Active'
);
CREATE TABLE IF NOT EXISTS courses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    credit_hours INTEGER DEFAULT 3,
    teacher      TEXT
);
CREATE TABLE IF NOT EXISTS enrollments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id  INTEGER NOT NULL REFERENCES courses(id)  ON DELETE CASCADE,
    UNIQUE (student_id, course_id)
);
CREATE TABLE IF NOT EXISTS attendance (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id  INTEGER NOT NULL REFERENCES courses(id)  ON DELETE CASCADE,
    att_date   TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('Present','Absent','Leave')),
    UNIQUE (student_id, course_id, att_date)
);
CREATE TABLE IF NOT EXISTS results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id     INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id      INTEGER NOT NULL REFERENCES courses(id)  ON DELETE CASCADE,
    exam_type      TEXT NOT NULL,
    total_marks    REAL NOT NULL,
    obtained_marks REAL NOT NULL,
    UNIQUE (student_id, course_id, exam_type)
);
CREATE TABLE IF NOT EXISTS fees (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    fee_month  TEXT NOT NULL,
    amount     REAL NOT NULL,
    paid       REAL NOT NULL DEFAULT 0,
    paid_date  TEXT,
    UNIQUE (student_id, fee_month)
);
"""

# A column that only the new schema has; used to detect old incompatible tables
_MARKERS = {
    "students": "roll_no",
    "courses": "code",
    "enrollments": "course_id",
    "attendance": "att_date",
    "results": "exam_type",
    "fees": "fee_month",
}


def sanitize_name(name):
    """Keep only letters, digits and underscores (safe for table/column/db names).
    Names that start with a digit get a leading underscore."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "", (name or "").strip())
    if cleaned and cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


def quote_ident(name):
    """Quote an SQL identifier so reserved words and odd names work."""
    return '"' + str(name).replace('"', '""') + '"'


def db_path(db_name):
    return os.path.join(DB_DIR, f"{db_name}.db")


def get_connection(db_name=None):
    """Open (and create if needed) the SQLite file for a department."""
    conn = sqlite3.connect(db_path(db_name or DEFAULT_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session(db_name=None):
    """Commit on success, roll back on error, ALWAYS close the connection."""
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
    """Create the student-system tables. An old table with the same name but a
    different structure (made with the old generic tool) is kept as <name>_legacyN."""
    with db_session(db_name) as conn:
        existing = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, marker in _MARKERS.items():
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({quote_ident(table)})")]
            if cols and marker not in cols:
                n = 1
                while f"{table}_legacy{n}" in existing:
                    n += 1
                new_name = f"{table}_legacy{n}"
                conn.execute(f"ALTER TABLE {quote_ident(table)} RENAME TO {quote_ident(new_name)}")
                existing.add(new_name)
        conn.executescript(SCHEMA)


def list_departments():
    names = [f[:-3] for f in os.listdir(DB_DIR) if f.endswith(".db")]
    return sorted(n for n in names if n != DEFAULT_DB)


def create_department(raw_name):
    """Returns (name, None) on success or (None, error_message) on failure."""
    name = sanitize_name(raw_name)
    if not name:
        return None, "Please enter a valid name (letters, numbers, underscore)."
    if name.lower() == DEFAULT_DB:
        return None, f"'{DEFAULT_DB}' is a reserved name."
    if name.lower() in (d.lower() for d in list_departments()):
        return None, f"Department '{name}' already exists."
    init_schema(name)
    return name, None


def delete_department(name):
    if name not in list_departments():
        raise FileNotFoundError(f"Department '{name}' not found.")
    os.remove(db_path(name))
