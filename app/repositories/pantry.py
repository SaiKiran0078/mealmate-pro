from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from ..core.stock import Batch, Stock
from ..core.units import format_quantity

def add_item(
    conn: sqlite3.Connection,
    user_id: int,
    ingredient_id: int,
    quantity: float,
    expires_on: date | None,
    entered_amount: float | None = None,
    entered_unit: str | None = None,
) -> int:
    """Save normalized stock quantity and the user's original measurement."""
    with conn:
        cur = conn.execute(
            """
            INSERT INTO pantry_items (
                user_id,
                ingredient_id,
                quantity,
                entered_amount,
                entered_unit,
                expires_on
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                ingredient_id,
                quantity,
                entered_amount,
                entered_unit,
                expires_on.isoformat() if expires_on else None,
            ),
        )

    return cur.lastrowid  # type: ignore[return-value]

def delete_item(conn: sqlite3.Connection, user_id: int, item_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id))
    return cur.rowcount > 0


def load_stock(conn: sqlite3.Connection, user_id: int) -> Stock:
    stock: Stock = {}
    rows = conn.execute(
        "SELECT id, ingredient_id, quantity, expires_on FROM pantry_items WHERE user_id = ? AND quantity > 0",
        (user_id,),
    )
    for r in rows:
        exp = date.fromisoformat(r["expires_on"]) if r["expires_on"] else None
        stock.setdefault(r["ingredient_id"], []).append(Batch(r["quantity"], exp, r["id"]))
    return stock


def list_items(conn: sqlite3.Connection, user_id: int, today: date | None = None) -> list[dict]:
    """Batches that still have stock. Depleted batches (quantity 0 after cooking) are not listed.

    ``display`` is the *remaining* amount. (The old UI showed what was originally typed in, so
    cooked-through ingredients kept their old numbers.)
    """
    today = today or date.today()
    rows = conn.execute(
        """
        SELECT p.id, i.name, i.category, i.base_unit, p.quantity, p.entered_amount, p.entered_unit, p.expires_on
        FROM pantry_items p
        JOIN ingredients i ON i.id = p.ingredient_id
        WHERE p.user_id = ? AND p.quantity > 0
        ORDER BY i.name, p.expires_on
        """,
        (user_id,),
    )
    out = []
    for row in rows:
        item = dict(row)
        item["display"] = format_quantity(item["quantity"], item["base_unit"])
        if item["expires_on"]:
            days = (date.fromisoformat(item["expires_on"]) - today).days
            item["days_left"] = days
            item["status"] = "expired" if days < 0 else "expiring" if days <= 3 else "ok"
        else:
            item["days_left"], item["status"] = None, "no_expiry"
        out.append(item)
    return out


def snapshot(conn: sqlite3.Connection, user_id: int, today: date, days: int = 3) -> dict:
    """One consistent set of pantry numbers, used by the overview page.

    ingredients  = distinct ingredients with usable (in-date, non-empty) stock
    expiring     = usable batches that expire within ``days`` days (today included)
    expired      = batches already past their date and still holding stock
    """
    items = list_items(conn, user_id, today)
    usable = [i for i in items if i["status"] != "expired"]

    def with_entered_measurement(item: dict) -> dict:
        # Keep the exact measurement the user entered for expiry reminders. Each batch
        # remains a separate row, so 1 kg and 4 pcs of the same ingredient are both shown.
        entered_amount, entered_unit = item.get("entered_amount"), item.get("entered_unit")
        if entered_amount is not None and entered_unit:
            amount = f"{entered_amount:g}"
            item = {**item, "display": f"{amount} {entered_unit}"}
        return item

    return {
        "ingredients": len({i["name"] for i in usable}),
        "batches": len(items),
        "expiring_soon": [with_entered_measurement(i) for i in usable if i["status"] == "expiring"],
        "expired": [with_entered_measurement(i) for i in items if i["status"] == "expired"],
    }


def summary(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    """Aggregation: total quantity, batch count and nearest expiry per ingredient."""
    rows = conn.execute(
        """SELECT i.id AS ingredient_id, i.name, i.category, i.base_unit,
                  SUM(p.quantity)   AS total_quantity,
                  COUNT(*)          AS batches,
                  MIN(p.expires_on) AS nearest_expiry
           FROM pantry_items p JOIN ingredients i ON i.id = p.ingredient_id
           WHERE p.user_id = ? AND p.quantity > 0
           GROUP BY i.id ORDER BY i.category, i.name""",
        (user_id,),
    )
    return [dict(r) for r in rows]


def expiring(conn: sqlite3.Connection, user_id: int, today: date, days: int = 3) -> list[dict]:
    rows = conn.execute(
        """SELECT p.id, i.name, i.base_unit, p.quantity, p.expires_on,
                  CAST(julianday(p.expires_on) - julianday(?) AS INTEGER) AS days_left
           FROM pantry_items p JOIN ingredients i ON i.id = p.ingredient_id
           WHERE p.user_id = ? AND p.quantity > 0 AND p.expires_on IS NOT NULL
             AND p.expires_on >= ? AND p.expires_on <= ?
           ORDER BY p.expires_on, i.name""",
        (today.isoformat(), user_id, today.isoformat(), (today + timedelta(days=days)).isoformat()),
    )
    return [dict(r) for r in rows]


def apply_deductions(conn: sqlite3.Connection, deductions: list[tuple[int | None, float]]) -> None:
    """Subtract used amounts from pantry rows. The caller owns the transaction."""
    for pantry_id, amount in deductions:
        if pantry_id is not None:
            conn.execute("UPDATE pantry_items SET quantity = MAX(quantity - ?, 0) WHERE id = ?", (amount, pantry_id))


def update_item(conn: sqlite3.Connection, user_id: int, item_id: int, *, quantity: float | None = None,
                entered_amount: float | None = None, entered_unit: str | None = None,
                expires_on: date | None = None, clear_expiry: bool = False) -> bool:
    """Edit one batch. Only the owner's rows can be changed. Returns False when the row does not exist."""
    sets, params = [], []
    if quantity is not None:
        sets += ["quantity = ?", "entered_amount = ?", "entered_unit = ?"]
        params += [quantity, entered_amount, entered_unit]
    if clear_expiry:
        sets.append("expires_on = NULL")
    elif expires_on is not None:
        sets.append("expires_on = ?")
        params.append(expires_on.isoformat())
    if not sets:
        return conn.execute("SELECT 1 FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id)).fetchone() is not None
    with conn:
        cur = conn.execute(f"UPDATE pantry_items SET {', '.join(sets)} WHERE id = ? AND user_id = ?", (*params, item_id, user_id))
    return cur.rowcount > 0
