from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..deps import Conn, CurrentUser, Today
from ..repositories import plans as plan_repo
from ..schemas import PlanIn
from ..serializers import plan_dict
from ..services import Conflict, NotFound, cook_meal, create_plan, saved_plan_grocery, saved_plan_view, swap_meal

router = APIRouter(prefix="/plans", tags=["meal plans"])


class SwapIn(BaseModel):
    recipe_id: int
    servings: int | None = Field(default=None, ge=1, le=12)


@router.post("/generate", status_code=201)
def generate(body: PlanIn, user: CurrentUser, conn: Conn, today: Today) -> dict:
    """Build a daily (days=1) or weekly (days=7) plan from your pantry, with a shopping list."""
    try:
        plan, plan_id = create_plan(conn, user, body, today)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = plan_dict(plan, body.daily_kcal or user.daily_kcal, plan_id)
    result["saved"] = plan_id is not None  # true only after the rows were written and read back
    return result


@router.get("")
def my_plans(user: CurrentUser, conn: Conn) -> list[dict]:
    return plan_repo.list_plans(conn, user.id)


@router.get("/stats")
def my_stats(user: CurrentUser, conn: Conn) -> dict:
    return {"most_cooked": plan_repo.most_cooked_recipes(conn, user.id)}


@router.get("/{plan_id}")
def get_plan(plan_id: int, user: CurrentUser, conn: Conn) -> dict:
    try:
        return saved_plan_view(conn, user, plan_id)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{plan_id}/grocery")
def plan_grocery(plan_id: int, user: CurrentUser, conn: Conn) -> list[dict]:
    try:
        return saved_plan_grocery(conn, user, plan_id)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{plan_id}/meals/{meal_id}/cook")
def mark_cooked(plan_id: int, meal_id: int, user: CurrentUser, conn: Conn, today: Today) -> dict:
    """Mark a meal as cooked: deducts the ingredients from your pantry, earliest expiry first."""
    try:
        return cook_meal(conn, user, plan_id, meal_id, today)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int, user: CurrentUser, conn: Conn) -> None:
    if not plan_repo.delete_plan(conn, user.id, plan_id):
        raise HTTPException(404, "Plan not found")


@router.put("/{plan_id}/meals/{meal_id}")
def replace_meal(plan_id: int, meal_id: int, body: SwapIn, user: CurrentUser, conn: Conn) -> dict:
    """Swap the recipe of one planned meal."""
    try:
        return swap_meal(conn, user, plan_id, meal_id, body.recipe_id, body.servings)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
