"""Small builders so tests can create ingredients and recipes in one line."""
from __future__ import annotations

from app.core.models import Ingredient, Nutrition, Recipe, RecipeIngredient


def make_ing(id: int, name: str, base: str = "g", staple: bool = False, **kw) -> Ingredient:
    return Ingredient(id=id, name=name, base_unit=base, is_staple=staple, **kw)


def make_recipe(
    id: int,
    title: str,
    items: list[tuple],  # (Ingredient, qty) or (Ingredient, qty, optional)
    meal_types: tuple[str, ...] = ("dinner",),
    servings: int = 2,
    cuisine: str = "other",
    diet_tags: tuple[str, ...] = (),
    kcal: float = 0.0,
    **kw,
) -> Recipe:
    ingredients = tuple(
        RecipeIngredient(i[0], i[1], optional=(len(i) > 2 and i[2])) for i in items
    )
    return Recipe(
        id=id, title=title, servings=servings, meal_types=meal_types, ingredients=ingredients,
        cuisine=cuisine, diet_tags=diet_tags, nutrition_per_serving=Nutrition(kcal=kcal), **kw,
    )
