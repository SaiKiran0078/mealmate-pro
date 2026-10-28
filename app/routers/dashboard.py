"""One endpoint that feeds the overview page.

Every number on the overview is computed here, in one place, from the database. (Before, the page derived
each stat from a different endpoint and shape: "recipe ideas" was simply the length of a list capped at 4,
the pantry count flipped between ingredients and batches, and expired food was reported as "expiring".)
"""
from __future__ import annotations

from fastapi import APIRouter

from ..core import matcher
from ..core.nutrition import progress_against_target
from ..deps import Conn, CurrentUser, Today
from ..repositories import pantry as pantry_repo
from ..repositories import plans as plan_repo
from ..repositories import recipes as recipe_repo
from ..serializers import match_dict

router = APIRouter(tags=["overview"])


@router.get("/dashboard")
def dashboard(user: CurrentUser, conn: Conn, today: Today) -> dict:
    recipes = recipe_repo.load_recipes(conn, user.id)
    stock = pantry_repo.load_stock(conn, user.id)
    pantry = pantry_repo.snapshot(conn, user.id, today)

    matches = matcher.suggest(recipes, stock, today, diet=user.diet, servings=user.household_size,
                              limit=max(len(recipes), 1))
    # a recipe made only of staples is not "cookable from your pantry"
    real = [m for m in matches if m.needed_count > 0]
    ready = [m for m in real if m.status == "ready"]
    almost = [m for m in real if m.status == "almost"]
    picks = [m for m in real if m.coverage > 0][:4]

    plans = plan_repo.list_plans(conn, user.id)
    by_id = {r.id: r for r in recipes}
    today_meals, planned_total = [], None
    for meal in plan_repo.meals_on(conn, user.id, today):
        recipe = by_id.get(meal["recipe_id"])
        if recipe is None:
            continue
        today_meals.append({"plan_id": meal["plan_id"], "meal_id": meal["id"], "meal_type": meal["meal_type"],
                            "title": recipe.title, "recipe_id": recipe.id, "cooked": bool(meal["cooked"])})
        planned_total = recipe.nutrition_per_serving if planned_total is None else planned_total + recipe.nutrition_per_serving

    return {
        "date": today.isoformat(),
        "pantry": {"ingredients": pantry["ingredients"], "batches": pantry["batches"],
                   "expiring_soon": pantry["expiring_soon"], "expired": pantry["expired"]},
        "recipes": {"catalog_size": len(recipes), "ready_to_cook": len(ready), "almost_ready": len(almost),
                    "picks": [match_dict(m) for m in picks]},
        "plans": {"count": len(plans), "latest": plans[0] if plans else None, "today": today_meals},
        "nutrition_today": {
            # per person: one serving of each planned meal vs. what the diary says was eaten
            "planned": progress_against_target(planned_total, user.daily_kcal)["totals"] if planned_total else None,
            "consumed": plan_repo.diary_totals(conn, user.id, today),
            "target_kcal": user.daily_kcal,
        },
    }
