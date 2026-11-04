"""Database helpers for the Dynamic EduManager (SQLite version)."""
import os
import re
import sqlite3
from contextlib import contextmanager

# Folder where department .db files live ("." = project folder, same as before)
DB_DIR = "."
DEFAULT_DB = "central_system"
SQLITE_TYPES = ["TEXT", "INTEGER", "REAL"]


def sanitize_name(name):
    """Keep only letters, digits and underscores (safe for table/column/db names).
    Names that start with a digit get a leading underscore."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "", (name or "").strip())
    if cleaned and cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


def quote_ident(name):
    """Quote an SQL identifier so reserved words (e.g. 'order') and odd names work."""
    return '"' + str(name).replace('"', '""') + '"'


def db_path(db_name):
    return os.path.join(DB_DIR, f"{db_name}.db")


def get_connection(db_name=None):
    """Open (and create if needed) the SQLite file for a department."""
    conn = sqlite3.connect(db_path(db_name or DEFAULT_DB))
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_session(db_name=None):
    """Commit on success, roll back on error, ALWAYS close the connection
    (an open connection would block file deletion on Windows)."""
    conn = get_connection(db_name)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
    with db_session(name) as conn:
        conn.execute("PRAGMA user_version = 1")  # forces the file to be created
    return name, None


def delete_department(name):
    if name not in list_departments():
        raise FileNotFoundError(f"Department '{name}' not found.")
    os.remove(db_path(name))
