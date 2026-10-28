"""Calories and macros."""
from __future__ import annotations

from collections.abc import Iterable

from .models import Ingredient, Nutrition, RecipeIngredient
from .units import to_grams

KCAL_PER_G = {"protein": 4, "carbs": 4, "fat": 9}


def ingredient_nutrition(ing: Ingredient, qty_base: float) -> Nutrition:
    f = to_grams(qty_base, ing) / 100.0
    return Nutrition(
        ing.kcal_per_100g * f,
        ing.protein_per_100g * f,
        ing.carbs_per_100g * f,
        ing.fat_per_100g * f,
    )


def recipe_nutrition(items: Iterable[RecipeIngredient], servings: int) -> tuple[Nutrition, bool]:
    """Return (nutrition per serving, is_complete).

    Optional ingredients (garnish) are left out. ``is_complete`` is False when
    some ingredient has no nutrition data, e.g. one imported from a web API.
    """
    total = Nutrition()
    complete = True
    for item in items:
        if item.optional:
            continue
        if not item.ingredient.nutrition_known:
            complete = False
            continue
        total = total + ingredient_nutrition(item.ingredient, item.quantity)
    return total.scaled(1.0 / max(servings, 1)), complete


def macro_split(n: Nutrition) -> dict[str, float]:
    """Share of calories coming from protein / carbs / fat, in percent."""
    cal = {k: getattr(n, k) * v for k, v in KCAL_PER_G.items()}
    total = sum(cal.values())
    if total <= 0:
        return {"protein_pct": 0.0, "carbs_pct": 0.0, "fat_pct": 0.0}
    return {f"{k}_pct": round(100 * v / total, 1) for k, v in cal.items()}


def progress_against_target(total: Nutrition, daily_kcal: int | None) -> dict:
    out = {"totals": total.as_dict(), "macro_split": macro_split(total)}
    if daily_kcal:
        out["target_kcal"] = daily_kcal
        out["percent_of_target"] = round(100 * total.kcal / daily_kcal)
    return out
