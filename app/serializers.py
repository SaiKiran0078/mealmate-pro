"""Turn engine objects into JSON-friendly dicts."""
from __future__ import annotations

from .core.cooking_guide import CookingGuide
from .core.matcher import Match
from .core.models import Recipe
from .core.nutrition import progress_against_target
from .core.planner import Plan


def recipe_summary(r: Recipe) -> dict:
    return {
        "id": r.id, "title": r.title, "description": r.description, "cuisine": r.cuisine,
        "meal_types": list(r.meal_types), "diet_tags": list(r.diet_tags), "servings": r.servings,
        "total_min": r.total_min, "difficulty": r.difficulty, "image_url": r.image_url, "source": r.source,
        "nutrition_per_serving": r.nutrition_per_serving.as_dict(), "nutrition_complete": r.nutrition_complete,
    }


def recipe_detail(r: Recipe) -> dict:
    from .core.units import format_quantity

    return {
        **recipe_summary(r),
        "ingredients": [
            {"name": i.ingredient.name, "quantity": format_quantity(i.quantity, i.ingredient.base_unit),
             "note": i.note, "optional": i.optional}
            for i in r.ingredients
        ],
        "steps": [
            {"number": s.number, "instruction": s.instruction, "duration_min": s.duration_min,
             "tip": s.tip, "passive": s.passive}
            for s in r.steps
        ],
    }


def match_dict(m: Match) -> dict:
    from .core.substitutions import suggest_substitutions
    from .core.units import format_quantity

    return {
        "recipe": recipe_summary(m.recipe),
        "score": round(m.score, 1),
        "coverage_pct": round(100 * m.coverage),
        "can_cook_now": m.can_cook_now,
        "status": m.status,
        "have_count": m.have_count,
        "needed_count": m.needed_count,
        "substitutions": suggest_substitutions([x.ingredient.name for x in m.missing]),
        "missing": [
            {"name": x.ingredient.name, "quantity": format_quantity(x.quantity, x.ingredient.base_unit)}
            for x in m.missing
        ],
        "uses_expiring": [{"name": e.ingredient.name, "days_left": e.days_left} for e in m.expiring],
        "why": m.reasons(),
    }


def guide_dict(g: CookingGuide) -> dict:
    return {
        "recipe_id": g.recipe_id, "title": g.title, "servings": g.servings, "difficulty": g.difficulty,
        "total_min": g.total_min, "can_cook_now": g.can_cook_now, "missing": g.missing,
        "ingredients": [vars(i) for i in g.ingredients],
        "mise_en_place": g.mise_en_place,
        "steps": [vars(s) for s in g.steps],
        "substitutions": g.substitutions,
        "nutrition_per_serving": g.nutrition_per_serving.as_dict(),
        "nutrition_complete": g.nutrition_complete,
    }


def plan_dict(plan: Plan, daily_kcal: int | None, plan_id: int | None = None) -> dict:
    return {
        "plan_id": plan_id,
        "start_date": plan.request.start.isoformat(),
        "days": [
            {
                "date": d.day.isoformat(),
                "meals": [
                    {
                        "meal_type": m.meal_type, "recipe_id": m.recipe.id, "title": m.recipe.title,
                        "servings": m.servings, "total_min": m.recipe.total_min,
                        "coverage_pct": round(100 * m.coverage), "missing": list(m.missing),
                        "uses_expiring": list(m.uses_expiring), "why": list(m.reasons),
                        "nutrition_per_serving": m.recipe.nutrition_per_serving.as_dict(),
                    }
                    for m in d.meals
                ],
                "nutrition": progress_against_target(d.nutrition, daily_kcal),
            }
            for d in plan.days
        ],
        "average_daily_nutrition": progress_against_target(plan.average_daily_nutrition(), daily_kcal),
        "grocery_list": [line.as_dict() for line in plan.grocery],
        "warnings": plan.warnings,
    }
