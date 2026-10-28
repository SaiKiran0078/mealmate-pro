"""Use-cases that combine repositories and the pure engine."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date

from .core.cooking_guide import build_guide
from .core.grocery import build_grocery_list, shortfall_for_meals
from .core.matcher import recipe_needs
from .core.models import Nutrition, User
from .core.nutrition import progress_against_target
from .core.planner import Plan, PlanRequest, generate_plan
from .core.stock import consume
from .repositories import ingredients as ingredient_repo
from .repositories import pantry as pantry_repo
from .repositories import plans as plan_repo
from .repositories import recipes as recipe_repo
from .schemas import PlanIn


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


def create_plan(conn: sqlite3.Connection, user: User, body: PlanIn, today: date) -> tuple[Plan, int | None]:
    request = PlanRequest(
        start=body.start_date or today,
        days=body.days,
        meals=tuple(body.meals),
        servings=body.servings or user.household_size,
        daily_kcal=body.daily_kcal or user.daily_kcal,
        diet=body.diet or user.diet,
        exclude_recipe_ids=frozenset(body.exclude_recipe_ids),
        max_repeats=body.max_repeats,
        max_minutes=body.max_minutes,
        pantry_first=body.pantry_first,
    )
    plan = generate_plan(
        recipe_repo.load_recipes(conn, user.id),
        pantry_repo.load_stock(conn, user.id),
        request,
        ingredient_repo.load_all(conn),
    )
    plan_id = None
    if body.save:
        if plan.meals():
            plan_id = plan_repo.save_plan(conn, user.id, plan)
            # Read it back: only report "saved" if the rows really are in the database.
            if plan_repo.get_plan_row(conn, user.id, plan_id) is None:
                raise RuntimeError("The plan could not be saved.")
        else:
            plan.warnings.append("Nothing was saved because no meals could be planned with these settings.")
    return plan, plan_id


def _load_saved(conn: sqlite3.Connection, user: User, plan_id: int):
    row = plan_repo.get_plan_row(conn, user.id, plan_id)
    if row is None:
        raise NotFound("Plan not found")
    meals = plan_repo.planned_meals(conn, plan_id)
    recipes = {r.id: r for r in recipe_repo.load_recipes(conn, user.id, sorted({m["recipe_id"] for m in meals}))}
    return row, meals, recipes


def saved_plan_view(conn: sqlite3.Connection, user: User, plan_id: int) -> dict:
    row, meals, recipes = _load_saved(conn, user, plan_id)
    by_day: dict[date, list[dict]] = defaultdict(list)
    for m in meals:
        by_day[m["meal_date"]].append(m)
    days = []
    for day, items in by_day.items():
        total = Nutrition()
        entries = []
        for m in items:
            r = recipes[m["recipe_id"]]
            total = total + r.nutrition_per_serving
            entries.append({
                "meal_id": m["id"], "meal_type": m["meal_type"], "recipe_id": r.id, "title": r.title,
                "servings": m["servings"], "total_min": r.total_min, "cooked": bool(m["cooked"]),
                "nutrition_per_serving": r.nutrition_per_serving.as_dict(),
            })
        days.append({"date": day.isoformat(), "meals": entries,
                     "nutrition": progress_against_target(total, user.daily_kcal)})
    return {"plan_id": plan_id, "start_date": row["start_date"], "days_count": row["days"], "servings": row["servings"],
            "days": days}


def swap_meal(conn: sqlite3.Connection, user: User, plan_id: int, meal_id: int, recipe_id: int, servings: int | None) -> dict:
    """Replace the recipe of a planned meal (not allowed once it has been cooked)."""
    if plan_repo.get_plan_row(conn, user.id, plan_id) is None:
        raise NotFound("Plan not found")
    meal = plan_repo.get_meal(conn, plan_id, meal_id)
    if meal is None:
        raise NotFound("Meal not found")
    if meal["cooked"]:
        raise Conflict("This meal is already cooked, so it cannot be replaced.")
    recipe = recipe_repo.get_recipe(conn, recipe_id, user.id)
    if recipe is None:
        raise NotFound("Recipe not found")
    plan_repo.replace_meal(conn, meal_id, recipe_id, servings)
    return {"meal_id": meal_id, "recipe_id": recipe.id, "title": recipe.title}


def saved_plan_grocery(conn: sqlite3.Connection, user: User, plan_id: int) -> list[dict]:
    """Shopping list for the meals not cooked yet, checked against today's pantry."""
    _, meals, recipes = _load_saved(conn, user, plan_id)
    todo = [(m["meal_date"], recipes[m["recipe_id"]], m["servings"]) for m in meals if not m["cooked"]]
    shortfall = shortfall_for_meals(todo, pantry_repo.load_stock(conn, user.id))
    return [line.as_dict() for line in build_grocery_list(shortfall, ingredient_repo.load_all(conn))]


def cook_meal(conn: sqlite3.Connection, user: User, plan_id: int, meal_id: int, today: date) -> dict:
    """Mark a planned meal as cooked and subtract the ingredients from the pantry (all or nothing)."""
    if plan_repo.get_plan_row(conn, user.id, plan_id) is None:
        raise NotFound("Plan not found")
    meal = plan_repo.get_meal(conn, plan_id, meal_id)
    if meal is None:
        raise NotFound("Meal not found")
    if meal["cooked"]:
        raise Conflict("This meal is already marked as cooked.")
    recipe = recipe_repo.get_recipe(conn, meal["recipe_id"], user.id)
    if recipe is None:
        raise NotFound("Recipe not found")

    stock = pantry_repo.load_stock(conn, user.id)
    result = consume(stock, recipe_needs(recipe, meal["servings"]), today)
    if result.shortfall:
        names = ingredient_repo.load_all(conn)
        raise Conflict("Missing ingredients: " + ", ".join(sorted(names[i].name for i in result.shortfall)))
    with conn:  # one transaction: either everything is deducted and marked, or nothing
        pantry_repo.apply_deductions(conn, result.deductions)
        plan_repo.mark_cooked(conn, meal_id)
    return {"meal_id": meal_id, "cooked": True, "recipe": recipe.title, "pantry_rows_updated": len(result.deductions)}


def recipe_guide(conn: sqlite3.Connection, user: User, recipe_id: int, servings: int | None, today: date):
    recipe = recipe_repo.get_recipe(conn, recipe_id, user.id)
    if recipe is None:
        raise NotFound("Recipe not found")
    return build_guide(recipe, pantry_repo.load_stock(conn, user.id), today, servings or user.household_size)
