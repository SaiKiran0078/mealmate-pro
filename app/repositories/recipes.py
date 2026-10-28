from __future__ import annotations

import sqlite3
from collections import defaultdict

from ..core.models import Recipe, RecipeIngredient, RecipeStep
from ..core.nutrition import recipe_nutrition
from . import ingredients as ingredient_repo


def _split(text: str) -> tuple[str, ...]:
    return tuple(p for p in (text or "").split(",") if p)


def insert_recipe(
    conn: sqlite3.Connection,
    *,
    title: str,
    meal_types: list[str],
    servings: int,
    ingredients: list[tuple[int, float, str, bool]],  # (ingredient_id, qty_base, note, optional)
    steps: list[dict],
    owner_id: int | None = None,
    description: str = "",
    cuisine: str = "other",
    prep_min: int = 0,
    cook_min: int = 0,
    difficulty: str = "easy",
    diet_tags: list[str] | None = None,
    source: str = "user",
    external_id: str | None = None,
    image_url: str | None = None,
) -> int:
    """Insert a recipe with its ingredients and steps. The caller owns the transaction."""
    cur = conn.execute(
        """INSERT INTO recipes (owner_id, title, description, cuisine, meal_types, servings, prep_min,
                                cook_min, difficulty, diet_tags, source, external_id, image_url)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (owner_id, title, description, cuisine, ",".join(meal_types), servings, prep_min, cook_min,
         difficulty, ",".join(diet_tags or []), source, external_id, image_url),
    )
    recipe_id = cur.lastrowid
    merged: dict[int, tuple[float, str, bool]] = {}
    for ing_id, qty, note, optional in ingredients:  # same ingredient twice -> add up
        old = merged.get(ing_id)
        merged[ing_id] = (qty + (old[0] if old else 0.0), note or (old[1] if old else ""), bool(optional) and (old[2] if old else True))
    conn.executemany(
        "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, note, optional) VALUES (?,?,?,?,?)",
        [(recipe_id, i, q, n, int(o)) for i, (q, n, o) in merged.items()],
    )
    conn.executemany(
        "INSERT INTO recipe_steps (recipe_id, step_no, instruction, duration_min, tip, passive) VALUES (?,?,?,?,?,?)",
        [(recipe_id, n, s["instruction"], s.get("duration_min"), s.get("tip"), int(bool(s.get("passive"))))
         for n, s in enumerate(steps, start=1)],
    )
    return recipe_id  # type: ignore[return-value]


def load_recipes(
    conn: sqlite3.Connection, user_id: int | None = None, ids: list[int] | None = None
) -> list[Recipe]:
    """Load recipes visible to ``user_id`` (shared catalog + their own) in 3 queries (no N+1)."""
    where, params = ["(r.owner_id IS NULL OR r.owner_id = ?)"], [user_id if user_id is not None else -1]
    if ids is not None:
        if not ids:
            return []
        where.append(f"r.id IN ({','.join('?' for _ in ids)})")
        params += ids
    clause = " AND ".join(where)

    recipe_rows = conn.execute(f"SELECT r.* FROM recipes r WHERE {clause} ORDER BY r.id", params).fetchall()
    if not recipe_rows:
        return []
    rid_marks = ",".join("?" for _ in recipe_rows)
    rids = [r["id"] for r in recipe_rows]

    all_ings = ingredient_repo.load_all(conn)
    items: dict[int, list[RecipeIngredient]] = defaultdict(list)
    for row in conn.execute(
        f"SELECT * FROM recipe_ingredients WHERE recipe_id IN ({rid_marks}) ORDER BY rowid", rids
    ):
        items[row["recipe_id"]].append(
            RecipeIngredient(all_ings[row["ingredient_id"]], row["quantity"], row["note"], bool(row["optional"]))
        )
    steps: dict[int, list[RecipeStep]] = defaultdict(list)
    for row in conn.execute(
        f"SELECT * FROM recipe_steps WHERE recipe_id IN ({rid_marks}) ORDER BY recipe_id, step_no", rids
    ):
        steps[row["recipe_id"]].append(
            RecipeStep(row["step_no"], row["instruction"], row["duration_min"], row["tip"], bool(row["passive"]))
        )

    recipes = []
    for r in recipe_rows:
        ing_list = items[r["id"]]
        nutrition, complete = recipe_nutrition(ing_list, r["servings"])
        recipes.append(
            Recipe(
                id=r["id"], title=r["title"], servings=r["servings"], meal_types=_split(r["meal_types"]),
                ingredients=tuple(ing_list), description=r["description"], cuisine=r["cuisine"],
                prep_min=r["prep_min"], cook_min=r["cook_min"], difficulty=r["difficulty"],
                diet_tags=_split(r["diet_tags"]), steps=tuple(steps[r["id"]]),
                nutrition_per_serving=nutrition, nutrition_complete=complete,
                source=r["source"], image_url=r["image_url"],
            )
        )
    return recipes


def get_recipe(conn: sqlite3.Connection, recipe_id: int, user_id: int | None = None) -> Recipe | None:
    found = load_recipes(conn, user_id, [recipe_id])
    return found[0] if found else None


def find_by_external(conn: sqlite3.Connection, source: str, external_id: str) -> int | None:
    r = conn.execute("SELECT id FROM recipes WHERE source = ? AND external_id = ?", (source, external_id)).fetchone()
    return r["id"] if r else None
