from __future__ import annotations

import sqlite3
from datetime import date

from ..core.planner import Plan


def save_plan(conn: sqlite3.Connection, user_id: int, plan: Plan) -> int:
    req = plan.request
    with conn:
        cur = conn.execute(
            "INSERT INTO meal_plans (user_id, start_date, days, servings) VALUES (?,?,?,?)",
            (user_id, req.start.isoformat(), req.days, req.servings),
        )
        plan_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO planned_meals (plan_id, meal_date, meal_type, recipe_id, servings) VALUES (?,?,?,?,?)",
            [(plan_id, m.day.isoformat(), m.meal_type, m.recipe.id, m.servings) for m in plan.meals()],
        )
    return plan_id  # type: ignore[return-value]


def get_plan_row(conn: sqlite3.Connection, user_id: int, plan_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM meal_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)).fetchone()


def list_plans(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT p.id, p.start_date, p.days, p.servings, p.created_at,
                  COUNT(m.id) AS meals, COALESCE(SUM(m.cooked), 0) AS cooked
           FROM meal_plans p LEFT JOIN planned_meals m ON m.plan_id = p.id
           WHERE p.user_id = ? GROUP BY p.id ORDER BY p.id DESC""",
        (user_id,),
    )
    return [dict(r) for r in rows]


def planned_meals(conn: sqlite3.Connection, plan_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, meal_date, meal_type, recipe_id, servings, cooked FROM planned_meals "
        "WHERE plan_id = ? ORDER BY meal_date, CASE meal_type WHEN 'breakfast' THEN 1 WHEN 'lunch' THEN 2 "
        "WHEN 'dinner' THEN 3 ELSE 4 END",
        (plan_id,),
    )
    return [{**dict(r), "meal_date": date.fromisoformat(r["meal_date"])} for r in rows]


def get_meal(conn: sqlite3.Connection, plan_id: int, meal_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM planned_meals WHERE id = ? AND plan_id = ?", (meal_id, plan_id)).fetchone()
    return {**dict(r), "meal_date": date.fromisoformat(r["meal_date"])} if r else None


def mark_cooked(conn: sqlite3.Connection, meal_id: int) -> None:
    conn.execute("UPDATE planned_meals SET cooked = 1 WHERE id = ?", (meal_id,))


def most_cooked_recipes(conn: sqlite3.Connection, user_id: int, limit: int = 5) -> list[dict]:
    """Aggregation across all plans: which recipes does this user actually cook?"""
    rows = conn.execute(
        """SELECT r.id, r.title, COUNT(*) AS times_cooked
           FROM planned_meals m JOIN meal_plans p ON p.id = m.plan_id JOIN recipes r ON r.id = m.recipe_id
           WHERE p.user_id = ? AND m.cooked = 1 GROUP BY r.id ORDER BY times_cooked DESC, r.title LIMIT ?""",
        (user_id, limit),
    )
    return [dict(r) for r in rows]


def delete_plan(conn: sqlite3.Connection, user_id: int, plan_id: int) -> bool:
    """Delete a plan and (via ON DELETE CASCADE) its meals. Pantry is not touched."""
    with conn:
        cur = conn.execute("DELETE FROM meal_plans WHERE id = ? AND user_id = ?", (plan_id, user_id))
    return cur.rowcount > 0


def replace_meal(conn: sqlite3.Connection, meal_id: int, recipe_id: int, servings: int | None = None) -> None:
    """Swap the recipe (and optionally the servings) of a meal that has not been cooked yet."""
    with conn:
        if servings is None:
            conn.execute("UPDATE planned_meals SET recipe_id = ? WHERE id = ? AND cooked = 0", (recipe_id, meal_id))
        else:
            conn.execute("UPDATE planned_meals SET recipe_id = ?, servings = ? WHERE id = ? AND cooked = 0",
                         (recipe_id, servings, meal_id))


def meals_on(conn: sqlite3.Connection, user_id: int, day: date) -> list[dict]:
    """What is planned for ``day``. If several saved plans cover the day, the newest plan wins per meal slot,
    so the same breakfast is never counted twice."""
    rows = conn.execute(
        """SELECT m.id, m.plan_id, m.meal_type, m.recipe_id, m.servings, m.cooked
           FROM planned_meals m JOIN meal_plans p ON p.id = m.plan_id
           WHERE p.user_id = ? AND m.meal_date = ? ORDER BY p.id DESC, m.id""",
        (user_id, day.isoformat()),
    )
    seen: set[str] = set()
    out = []
    for r in rows:
        if r["meal_type"] in seen:
            continue
        seen.add(r["meal_type"])
        out.append(dict(r))
    order = {"breakfast": 1, "lunch": 2, "dinner": 3, "snack": 4}
    return sorted(out, key=lambda m: order.get(m["meal_type"], 9))


def diary_totals(conn: sqlite3.Connection, user_id: int, day: date) -> dict:
    r = conn.execute(
        """SELECT COUNT(*) AS entries, COALESCE(SUM(kcal),0) AS kcal, COALESCE(SUM(protein_g),0) AS protein_g,
                  COALESCE(SUM(carbs_g),0) AS carbs_g, COALESCE(SUM(fat_g),0) AS fat_g
           FROM food_diary WHERE user_id = ? AND consumed_on = ?""",
        (user_id, day.isoformat()),
    ).fetchone()
    return {"entries": r["entries"], **{k: round(r[k], 1) for k in ("kcal", "protein_g", "carbs_g", "fat_g")}}
