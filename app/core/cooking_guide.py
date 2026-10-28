"""Step-by-step cooking guide for one recipe, tailored to what is in the pantry."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .matcher import evaluate
from .models import Nutrition, Recipe
from .stock import EPS, Stock, available
from .substitutions import suggest_substitutions
from .units import format_quantity


@dataclass(frozen=True)
class GuideIngredient:
    name: str
    quantity: str
    note: str
    optional: bool
    status: str  # in_pantry | partial | missing | staple


@dataclass(frozen=True)
class GuideStep:
    number: int
    instruction: str
    duration_min: int | None
    tip: str | None
    passive: bool
    starts_at_min: int  # approximate minutes from the start of cooking


@dataclass(frozen=True)
class CookingGuide:
    recipe_id: int
    title: str
    servings: int
    difficulty: str
    total_min: int
    ingredients: list[GuideIngredient]
    mise_en_place: list[str]
    steps: list[GuideStep]
    substitutions: dict[str, list[str]]
    nutrition_per_serving: Nutrition
    nutrition_complete: bool
    can_cook_now: bool
    missing: list[str]


def _status(recipe_item, stock: Stock, on: date, scale: float) -> str:
    ing = recipe_item.ingredient
    if ing.is_staple:
        return "staple"
    need = recipe_item.quantity * scale
    have = available(stock, ing.id, on)
    if have + EPS >= need:
        return "in_pantry"
    return "partial" if have > EPS else "missing"


def build_guide(recipe: Recipe, stock: Stock, on: date, servings: int | None = None) -> CookingGuide:
    servings = servings or recipe.servings
    scale = servings / recipe.servings

    ingredients = []
    mise = ["Read the whole recipe once, then put every ingredient and a clean board and knife within reach."]
    for item in recipe.ingredients:
        qty = format_quantity(item.quantity * scale, item.ingredient.base_unit)
        ingredients.append(
            GuideIngredient(item.ingredient.name, qty, item.note, item.optional, _status(item, stock, on, scale))
        )
        if item.note:
            mise.append(f"{item.ingredient.name.capitalize()} ({qty}): {item.note}.")

    steps, clock = [], 0
    for s in recipe.steps:
        steps.append(GuideStep(s.number, s.instruction, s.duration_min, s.tip, s.passive, clock))
        clock += s.duration_min or 0

    match = evaluate(recipe, stock, on, servings)
    missing = [m.ingredient.name for m in match.missing]
    return CookingGuide(
        recipe_id=recipe.id,
        title=recipe.title,
        servings=servings,
        difficulty=recipe.difficulty,
        total_min=recipe.total_min,
        ingredients=ingredients,
        mise_en_place=mise,
        steps=steps,
        substitutions=suggest_substitutions(missing),
        nutrition_per_serving=recipe.nutrition_per_serving,
        nutrition_complete=recipe.nutrition_complete,
        can_cook_now=match.can_cook_now,
        missing=missing,
    )
