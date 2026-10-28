from __future__ import annotations

import sqlite3

from ..core import names
from ..core.models import Ingredient
from ..core.units import UnitError, normalize_unit


def _row(r: sqlite3.Row) -> Ingredient:
    return Ingredient(
        id=r["id"], name=r["name"], base_unit=r["base_unit"], category=r["category"],
        is_staple=bool(r["is_staple"]), density_g_per_ml=r["density_g_per_ml"],
        grams_per_piece=r["grams_per_piece"], kcal_per_100g=r["kcal_per_100g"],
        protein_per_100g=r["protein_per_100g"], carbs_per_100g=r["carbs_per_100g"],
        fat_per_100g=r["fat_per_100g"], nutrition_known=bool(r["nutrition_known"]),
    )


def create(conn: sqlite3.Connection, **f) -> Ingredient:
    cols = ", ".join(f)
    marks = ", ".join("?" for _ in f)
    cur = conn.execute(f"INSERT INTO ingredients ({cols}) VALUES ({marks})", tuple(f.values()))
    return get(conn, cur.lastrowid)  # type: ignore[arg-type,return-value]


def get(conn: sqlite3.Connection, ingredient_id: int) -> Ingredient | None:
    r = conn.execute("SELECT * FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()
    return _row(r) if r else None


def get_by_name(conn: sqlite3.Connection, name: str) -> Ingredient | None:
    r = conn.execute("SELECT * FROM ingredients WHERE name = ?", (name.strip(),)).fetchone()
    return _row(r) if r else None


def search(conn: sqlite3.Connection, q: str = "", limit: int = 20) -> list[Ingredient]:
    rows = conn.execute(
        "SELECT * FROM ingredients WHERE name LIKE ? ORDER BY name LIMIT ?", (f"%{q.strip()}%", limit)
    ).fetchall()
    return [_row(r) for r in rows]


def load_all(conn: sqlite3.Connection) -> dict[int, Ingredient]:
    return {r["id"]: _row(r) for r in conn.execute("SELECT * FROM ingredients")}


def load_all_by_name(conn: sqlite3.Connection) -> dict[str, Ingredient]:
    return {i.name.lower(): i for i in load_all(conn).values()}


def resolve(conn: sqlite3.Connection, name: str) -> Ingredient | None:
    """Find an existing ingredient for typed text (plurals, spelling variants, aliases)."""
    return names.resolve(name, load_all_by_name(conn))


def suggestions_for(conn: sqlite3.Connection, name: str) -> list[str]:
    return names.similar(name, [i.name for i in load_all(conn).values()])


def find_or_create(conn: sqlite3.Connection, name: str, unit_hint: str | None = None) -> Ingredient:
    """Look an ingredient up by name; create it (without nutrition data) if it is new.

    Lookup tolerates plurals and common aliases ("tomatoes" -> "tomato", "chicken" -> "chicken breast"),
    so pantry items line up with the recipes that use them. ``unit_hint`` (any unit text, e.g. "cup")
    decides the base unit of a *new* ingredient.
    """
    found = resolve(conn, name)
    if found:
        return found
    clean = names.normalize(name) or name.strip().lower()
    try:
        hint = normalize_unit(unit_hint) if unit_hint else None
    except UnitError:
        hint = None
    volume = {"ml", "l", "tsp", "tbsp", "cup"}
    base = "pcs" if hint == "pcs" else "ml" if hint in volume else "g"
    return create(conn, name=clean, base_unit=base, category="imported", nutrition_known=0)


def repair_duplicates(conn: sqlite3.Connection) -> int:
    """Merge ingredients that the old name lookup created by mistake (e.g. "tomatoes" next to "tomato").

    Only auto-created ones (category 'imported', no nutrition) are merged into the real catalog entry that
    :func:`names.resolve` picks. Pantry rows and recipe lines are moved over, converting units through grams
    when the base units differ; anything that cannot be converted safely is left alone. Idempotent.
    Returns the number of ingredients merged.
    """
    from ..core.units import to_grams

    everything = load_all(conn)
    canonical = {i.name.lower(): i for i in everything.values() if i.category != "imported" or i.nutrition_known}
    merged = 0
    for dup in [i for i in everything.values() if i.category == "imported" and not i.nutrition_known]:
        target = names.resolve(dup.name, canonical)
        if target is None or target.id == dup.id:
            continue

        def convert(qty: float, _dup=dup, _target=target) -> float | None:
            if _dup.base_unit == _target.base_unit:
                return qty
            grams = to_grams(qty, _dup)
            if grams <= 0:
                return None
            if _target.base_unit == "g":
                return grams
            if _target.base_unit == "ml":
                return grams / _target.density_g_per_ml
            return grams / _target.grams_per_piece if _target.grams_per_piece else None

        with conn:
            for row in conn.execute("SELECT id, quantity FROM pantry_items WHERE ingredient_id = ?", (dup.id,)).fetchall():
                qty = convert(row["quantity"])
                if qty is not None:
                    conn.execute(
                        "UPDATE pantry_items SET ingredient_id = ?, quantity = ?, entered_amount = NULL, entered_unit = NULL "
                        "WHERE id = ?", (target.id, qty, row["id"]))
            for row in conn.execute("SELECT recipe_id, quantity, note, optional FROM recipe_ingredients "
                                    "WHERE ingredient_id = ?", (dup.id,)).fetchall():
                qty = convert(row["quantity"])
                if qty is None:
                    continue
                clash = conn.execute("SELECT quantity FROM recipe_ingredients WHERE recipe_id = ? AND ingredient_id = ?",
                                     (row["recipe_id"], target.id)).fetchone()
                if clash:
                    conn.execute("UPDATE recipe_ingredients SET quantity = quantity + ? WHERE recipe_id = ? AND ingredient_id = ?",
                                 (qty, row["recipe_id"], target.id))
                    conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ? AND ingredient_id = ?",
                                 (row["recipe_id"], dup.id))
                else:
                    conn.execute("UPDATE recipe_ingredients SET ingredient_id = ?, quantity = ? "
                                 "WHERE recipe_id = ? AND ingredient_id = ?", (target.id, qty, row["recipe_id"], dup.id))
            left = conn.execute("SELECT (SELECT COUNT(*) FROM pantry_items WHERE ingredient_id = ?) + "
                                "(SELECT COUNT(*) FROM recipe_ingredients WHERE ingredient_id = ?) AS n",
                                (dup.id, dup.id)).fetchone()["n"]
            if left == 0:
                conn.execute("DELETE FROM ingredients WHERE id = ?", (dup.id,))
                merged += 1
    return merged
