"""Load the built-in catalog into an empty database."""
from __future__ import annotations

import sqlite3

from ..core.units import to_base
from ..repositories import ingredients as ingredient_repo
from ..repositories import recipes as recipe_repo
from .catalog import INGREDIENTS, RECIPES


def seed_if_empty(conn: sqlite3.Connection) -> bool:
    """Insert ingredients and recipes once. Returns True if anything was added."""
    if conn.execute("SELECT 1 FROM ingredients LIMIT 1").fetchone():
        return False
    with conn:
        for name, base, cat, staple, kcal, p, c, f, gpp, density in INGREDIENTS:
            ingredient_repo.create(
                conn, name=name, base_unit=base, category=cat, is_staple=bool(staple),
                density_g_per_ml=density, grams_per_piece=gpp,
                kcal_per_100g=kcal, protein_per_100g=p, carbs_per_100g=c, fat_per_100g=f,
            )
        by_name = ingredient_repo.load_all_by_name(conn)
        for r in RECIPES:
            items = []
            for name, amount, unit, note, optional in r["ingredients"]:
                ing = by_name[name]
                items.append((ing.id, to_base(amount, unit, ing), note, optional))
            steps = [
                {"instruction": t, "duration_min": m, "tip": tip, "passive": passive}
                for t, m, tip, passive in r["steps"]
            ]
            recipe_repo.insert_recipe(
                conn,
                owner_id=None, source="seed",
                **{k: r[k] for k in (
                    "title", "description", "cuisine", "meal_types", "servings",
                    "prep_min", "cook_min", "difficulty", "diet_tags")},
                ingredients=items, steps=steps,
            )
    return True


def seed_missing_recipes(conn: sqlite3.Connection) -> int:
    """Add newly released built-in recipes to existing databases without duplicating rows."""
    if not conn.execute("SELECT 1 FROM ingredients LIMIT 1").fetchone():
        return 0
    existing = {row[0] for row in conn.execute("SELECT title FROM recipes WHERE source = 'seed'")}
    pending = [recipe for recipe in RECIPES if recipe["title"] not in existing]
    if not pending:
        return 0
    by_name = ingredient_repo.load_all_by_name(conn)
    inserted = 0
    with conn:
        for recipe in pending:
            # Older user databases may lack ingredients introduced by newer catalog versions.
            for name, base, cat, staple, kcal, protein, carbs, fat, grams_per_piece, density in INGREDIENTS:
                if name not in by_name:
                    ingredient_repo.create(conn, name=name, base_unit=base, category=cat, is_staple=bool(staple),
                        density_g_per_ml=density, grams_per_piece=grams_per_piece, kcal_per_100g=kcal,
                        protein_per_100g=protein, carbs_per_100g=carbs, fat_per_100g=fat)
            by_name = ingredient_repo.load_all_by_name(conn)
            items = [(by_name[name].id, to_base(amount, unit, by_name[name]), note, optional)
                     for name, amount, unit, note, optional in recipe["ingredients"]]
            steps = [{"instruction": text, "duration_min": minutes, "tip": tip, "passive": passive}
                     for text, minutes, tip, passive in recipe["steps"]]
            recipe_repo.insert_recipe(conn, owner_id=None, source="seed",
                **{key: recipe[key] for key in ("title", "description", "cuisine", "meal_types", "servings",
                                                "prep_min", "cook_min", "difficulty", "diet_tags")},
                ingredients=items, steps=steps)
            inserted += 1
    return inserted
