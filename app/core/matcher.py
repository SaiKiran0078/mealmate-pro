"""Pantry matching: "what can I cook with what I have?".

For every recipe we compute
  * coverage - how much of the recipe the pantry already covers (0..1)
  * missing  - what is still needed
  * urgency  - how much the recipe helps use up food that is about to expire
and blend them into one explainable score.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .models import Ingredient, Recipe
from .stock import EPS, Stock, available, usable

EXPIRY_WINDOW_DAYS = 3
COVERAGE_WEIGHT = 0.7
URGENCY_WEIGHT = 0.3


@dataclass(frozen=True)
class MissingItem:
    ingredient: Ingredient
    quantity: float  # still needed, base unit


@dataclass(frozen=True)
class ExpiringUse:
    ingredient: Ingredient
    days_left: int


@dataclass(frozen=True)
class Match:
    recipe: Recipe
    servings: int
    coverage: float
    have_count: int
    needed_count: int
    missing: tuple[MissingItem, ...]
    expiring: tuple[ExpiringUse, ...]
    urgency: float
    score: float

    @property
    def can_cook_now(self) -> bool:
        return not self.missing

    @property
    def status(self) -> str:
        """ready = everything essential is in the pantry; almost = at most 2 items missing and
        at least half covered; otherwise missing."""
        if not self.missing:
            return "ready"
        return "almost" if len(self.missing) <= 2 and self.coverage >= 0.5 else "missing"

    def reasons(self) -> list[str]:
        out = [f"You have {self.have_count} of {self.needed_count} key ingredients."]
        for use in self.expiring:
            when = "today" if use.days_left <= 0 else f"in {use.days_left} day{'s' if use.days_left != 1 else ''}"
            out.append(f"Uses {use.ingredient.name}, which expires {when}.")
        if self.missing and len(self.missing) <= 3:
            out.append("Only missing: " + ", ".join(m.ingredient.name for m in self.missing) + ".")
        return out


def recipe_needs(recipe: Recipe, servings: int | None = None) -> dict[int, float]:
    """Ingredient quantities to buy/consume (staples and optional items excluded)."""
    scale = (servings or recipe.servings) / recipe.servings
    needs: dict[int, float] = {}
    for item in recipe.ingredients:
        if item.optional or item.ingredient.is_staple:
            continue
        needs[item.ingredient.id] = needs.get(item.ingredient.id, 0.0) + item.quantity * scale
    return needs


def evaluate(
    recipe: Recipe,
    stock: Stock,
    on: date,
    servings: int | None = None,
    window: int = EXPIRY_WINDOW_DAYS,
) -> Match:
    servings = servings or recipe.servings
    needs = recipe_needs(recipe, servings)
    by_id = {i.ingredient.id: i.ingredient for i in recipe.ingredients}

    ratios: list[float] = []
    missing: list[MissingItem] = []
    expiring: list[ExpiringUse] = []
    for ing_id, need in needs.items():
        have = available(stock, ing_id, on)
        ratios.append(min(have / need, 1.0))
        if have + EPS < need:
            missing.append(MissingItem(by_id[ing_id], need - have))
        if have > EPS:
            days = [
                (b.expires_on - on).days
                for b in stock.get(ing_id, [])
                if usable(b, on) and b.expires_on is not None and (b.expires_on - on).days <= window
            ]
            if days:
                expiring.append(ExpiringUse(by_id[ing_id], min(days)))

    coverage = sum(ratios) / len(ratios) if ratios else 1.0
    urgency = min(1.0, sum(1.0 / (1 + e.days_left) for e in expiring) / 2) if expiring else 0.0
    score = 100 * (COVERAGE_WEIGHT * coverage + URGENCY_WEIGHT * urgency)
    return Match(
        recipe=recipe,
        servings=servings,
        coverage=coverage,
        have_count=sum(1 for r in ratios if r >= 1.0 - EPS),
        needed_count=len(ratios),
        missing=tuple(sorted(missing, key=lambda m: m.ingredient.name)),
        expiring=tuple(sorted(expiring, key=lambda e: (e.days_left, e.ingredient.name))),
        urgency=urgency,
        score=score,
    )


def matches_diet(recipe: Recipe, diet: str | None) -> bool:
    if not diet:
        return True
    if diet == "non_vegetarian":
        # Non-vegetarian means meat and vegetarian recipes are both allowed; it should not
        # force every slot to be meat-based (many breakfast/snack recipes are vegetarian).
        return True
    return diet in recipe.diet_tags


def eligible(
    recipe: Recipe,
    meal_type: str | None = None,
    diet: str | None = None,
    max_minutes: int | None = None,
    exclude_ids: Iterable[int] = (),
) -> bool:
    return (
        (meal_type is None or meal_type in recipe.meal_types)
        and matches_diet(recipe, diet)
        and (max_minutes is None or recipe.total_min <= max_minutes)
        and recipe.id not in set(exclude_ids)
    )


def suggest(
    recipes: Iterable[Recipe],
    stock: Stock,
    on: date,
    *,
    meal_type: str | None = None,
    diet: str | None = None,
    max_minutes: int | None = None,
    servings: int | None = None,
    min_coverage: float = 0.0,
    only_cookable: bool = False,
    limit: int = 10,
) -> list[Match]:
    """Rank recipes by how well they fit the pantry (best first)."""
    matches = [
        evaluate(r, stock, on, servings)
        for r in recipes
        if eligible(r, meal_type, diet, max_minutes)
    ]
    matches = [
        m for m in matches
        if m.coverage >= min_coverage and (m.can_cook_now or not only_cookable)
    ]
    matches.sort(key=lambda m: (-m.score, m.recipe.title))
    return matches[:limit]
