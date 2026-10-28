from __future__ import annotations

import sqlite3

from ..core.models import User


def _row(r: sqlite3.Row) -> User:
    return User(r["id"], r["email"], r["daily_kcal"], r["diet"], r["household_size"])


def create(conn: sqlite3.Connection, email: str, password_hash: str) -> User:
    with conn:
        cur = conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email.strip(), password_hash))
    return get(conn, cur.lastrowid)  # type: ignore[arg-type]


def get(conn: sqlite3.Connection, user_id: int) -> User | None:
    r = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row(r) if r else None


def get_with_hash(conn: sqlite3.Connection, email: str) -> tuple[User, str] | None:
    r = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip(),)).fetchone()
    return (_row(r), r["password_hash"]) if r else None


def update_profile(conn: sqlite3.Connection, user_id: int, daily_kcal: int | None, diet: str | None, household_size: int) -> User:
    with conn:
        conn.execute(
            "UPDATE users SET daily_kcal = ?, diet = ?, household_size = ? WHERE id = ?",
            (daily_kcal, diet, household_size, user_id),
        )
    return get(conn, user_id)  # type: ignore[return-value]
