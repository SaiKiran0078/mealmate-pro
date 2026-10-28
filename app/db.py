"""SQLite connection helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")

    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create database tables and safely migrate existing databases."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(pantry_items)")
    }

    if "entered_amount" not in columns:
        conn.execute(
            "ALTER TABLE pantry_items ADD COLUMN entered_amount REAL"
        )

    if "entered_unit" not in columns:
        conn.execute(
            "ALTER TABLE pantry_items ADD COLUMN entered_unit TEXT"
        )

    conn.commit()
