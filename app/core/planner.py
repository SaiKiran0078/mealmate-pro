"""Meal plan generator (daily or weekly).

Greedy, pantry-aware planning:

  for each day -> for each meal slot:
      score every eligible recipe against a *simulated* pantry
      pick the best, "cook" it in the simulation (first-expiring-first-out)
      remember whatever we were short of -> that becomes the grocery list

Because the simulation really consumes the pantry, two recipes can never claim
the same 200 g of lentils, and the shopping list is exact.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from .grocery import GroceryLine, build_grocery_list
from .matcher import Match, eligible, evaluate, recipe_needs
from .models import MEAL_TYPES, Ingredient, Nutrition, Recipe
from .stock import EPS, Stock, clone, consume
from .units import format_quantity

MEAL_SHARE = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.40, "snack": 0.10}

# Score weights (sum to 100). Documented in docs/ARCHITECTURE.md.
W_COVERAGE, W_URGENCY, W_KCAL_FIT, W_VARIETY, W_SHARED_SHOPPING = 50, 20, 15, 10, 5
REPEAT_PENALTY = 12


@dataclass(frozen=True)
class PlanRequest:
    start: date
    days: int = 7
    meals: tuple[str, ...] = ("breakfast", "lunch", "dinner")
    servings: int = 1  # portions cooked per meal (scales ingredient quantities)
    daily_kcal: float | None = None  # per person
    diet: str | None = None
    exclude_recipe_ids: frozenset[int] = frozenset()
    max_repeats: int = 2  # how many times one recipe may appear in the plan
    max_minutes: int | None = None
    pantry_first: bool = True

    def validate(self) -> None:
        if not 1 <= self.days <= 14:
            raise ValueError("days must be between 1 and 14")
        if not self.meals or any(m not in MEAL_TYPES for m in self.meals):
            raise ValueError(f"meals must be a non-empty subset of {MEAL_TYPES}")
        if self.servings < 1:
            raise ValueError("servings must be at least 1")
        if self.max_repeats < 1:
            raise ValueError("max_repeats must be at least 1")


@dataclass(frozen=True)
class PlannedMeal:
    day: date
    meal_type: str
    recipe: Recipe
    servings: int
    coverage: float
    uses_expiring: tuple[str, ...]
    missing: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass
class DayPlan:
    day: date
    meals: list[PlannedMeal] = field(default_factory=list)

    @property
    def nutrition(self) -> Nutrition:
        """What one person eats this day (per-serving nutrition of each meal)."""
        total = Nutrition()
        for m in self.meals:
            total = total + m.recipe.nutrition_per_serving
        return total


@dataclass
class Plan:
    request: PlanRequest
    days: list[DayPlan]
    shortfall: dict[int, float]
    grocery: list[GroceryLine]
    warnings: list[str]

    def meals(self) -> list[PlannedMeal]:
        return [m for d in self.days for m in d.meals]

    def average_daily_nutrition(self) -> Nutrition:
        if not self.days:
            return Nutrition()
        total = Nutrition()
        for d in self.days:
            total = total + d.nutrition
        return total.scaled(1 / len(self.days))


def _meal_targets(request: PlanRequest, meals: list[str]) -> dict[str, float | None]:
    if not request.daily_kcal:
        return {m: None for m in meals}
    weight = sum(MEAL_SHARE[m] for m in meals)
    return {m: request.daily_kcal * MEAL_SHARE[m] / weight for m in meals}


def _slot_score(
    match: Match,
    target_kcal: float | None,
    prev_cuisine: str | None,
    times_used: int,
    to_buy: dict[int, float],
) -> float:
    r = match.recipe
    kcal_fit = 0.5  # neutral when the user gave no calorie target
    if target_kcal:
        kcal_fit = 1 - min(abs(r.nutrition_per_serving.kcal - target_kcal) / target_kcal, 1.0)
    variety = 0.0 if (prev_cuisine and r.cuisine == prev_cuisine) else 1.0
    shared = 0.0
    if match.missing:
        shared = sum(1 for m in match.missing if m.ingredient.id in to_buy) / len(match.missing)
    return (
        W_COVERAGE * match.coverage
        + W_URGENCY * match.urgency
        + W_KCAL_FIT * kcal_fit
        + W_VARIETY * variety
        + W_SHARED_SHOPPING * shared
        - REPEAT_PENALTY * times_used
    )


def generate_plan(
    recipes: list[Recipe],
    stock: Stock,
    request: PlanRequest,
    ingredients: dict[int, Ingredient],
) -> Plan:
    request.validate()
    meals = sorted(set(request.meals), key=MEAL_TYPES.index)
    targets = _meal_targets(request, meals)

    sim = clone(stock)  # never touch the real pantry while planning
    used: Counter[int] = Counter()
    to_buy: dict[int, float] = {}
    warnings: list[str] = []
    days: list[DayPlan] = []
    prev_cuisine: str | None = None

    for offset in range(request.days):
        day = request.start + timedelta(days=offset)
        day_plan = DayPlan(day)
        for meal in meals:
            pool = [
                r for r in recipes
                if eligible(r, meal, request.diet, max_minutes=request.max_minutes, exclude_ids=request.exclude_recipe_ids)
            ]
            fresh = [r for r in pool if used[r.id] < request.max_repeats]
            if pool and not fresh:
                warnings.append(f"Not enough different {meal} recipes: some repeat more than {request.max_repeats}x.")
                fresh = pool
            if not fresh:
                warnings.append(f"No {meal} recipe matches your filters for {day.isoformat()}.")
                continue

            scored = []
            for r in fresh:
                m = evaluate(r, sim, day, request.servings)
                score = _slot_score(m, targets[meal], prev_cuisine, used[r.id], to_buy)
                # Pantry-first mode strongly favours dishes the available stock can actually cover.
                if request.pantry_first:
                    score += 10 * m.coverage
                    score -= 2 * len(m.missing)
                scored.append((score, -r.id, m))
            _, _, best = max(scored, key=lambda t: (t[0], t[1]))

            result = consume(sim, recipe_needs(best.recipe, request.servings), day)
            for ing_id, qty in result.shortfall.items():
                to_buy[ing_id] = to_buy.get(ing_id, 0.0) + qty
            used[best.recipe.id] += 1
            prev_cuisine = best.recipe.cuisine
            day_plan.meals.append(
                PlannedMeal(
                    day=day,
                    meal_type=meal,
                    recipe=best.recipe,
                    servings=request.servings,
                    coverage=round(best.coverage, 2),
                    uses_expiring=tuple(e.ingredient.name for e in best.expiring),
                    missing=tuple(m.ingredient.name for m in best.missing),
                    reasons=tuple(best.reasons()),
                )
            )
        days.append(day_plan)

    end = request.start + timedelta(days=request.days - 1)
    for ing_id, batches in sim.items():
        for b in batches:
            if b.qty > EPS and b.expires_on is not None and request.start <= b.expires_on <= end:
                ing = ingredients.get(ing_id)
                if ing:
                    warnings.append(
                        f"{ing.name} ({format_quantity(b.qty, ing.base_unit)}) expires on "
                        f"{b.expires_on.isoformat()} and is not used in this plan."
                    )

    warnings.extend(_calorie_warning(request, days, meals))
    return Plan(request, days, to_buy, build_grocery_list(to_buy, ingredients), warnings)


def _calorie_warning(request: PlanRequest, days: list[DayPlan], meals: list[str]) -> list[str]:
    """Be honest when the plan misses the calorie target by more than 15%."""
    filled = [d for d in days if d.meals]
    if not request.daily_kcal or not filled:
        return []
    average = sum(d.nutrition.kcal for d in filled) / len(filled)
    gap = (average - request.daily_kcal) / request.daily_kcal
    if abs(gap) <= 0.15:
        return []
    side = "below" if gap < 0 else "above"
    text = (
        f"The plan averages {round(average)} kcal per day, {round(abs(gap) * 100)}% {side} "
        f"your {round(request.daily_kcal)} kcal target."
    )
    if gap < 0 and "snack" not in meals:
        text += " Add 'snack' to the meals list to close the gap."
    return [text]
