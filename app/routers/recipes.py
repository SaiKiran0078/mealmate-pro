from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from ..core import matcher
from ..core import search as recipe_search
from ..core.models import MEAL_TYPES
from ..core.units import to_base
from ..deps import Conn, CurrentUser, Today
from ..integrations import themealdb
from ..repositories import ingredients as ingredient_repo
from ..repositories import pantry as pantry_repo
from ..repositories import recipes as recipe_repo
from ..schemas import RecipeIn
from ..serializers import guide_dict, match_dict, recipe_detail, recipe_summary
from ..services import NotFound, recipe_guide

router = APIRouter(prefix="/recipes", tags=["recipes"])


class RecipeFeedbackIn(BaseModel):
    favorite: bool | None = None
    rating: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def require_a_change(self):
        if self.favorite is None and self.rating is None:
            raise ValueError("Provide favorite and/or a rating from 1 to 5.")
        return self


@router.get("")
def list_recipes(
    user: CurrentUser,
    conn: Conn,
    q: str = Query("", max_length=120),
    meal_type: str | None = Query(None, pattern="^(breakfast|lunch|dinner|snack)$"),
    diet: str | None = Query(None, pattern="^(vegetarian|vegan|gluten_free)$"),
    max_minutes: int | None = Query(None, ge=1, le=600),
) -> list[dict]:
    """Plain list of recipes (kept for compatibility). ``q`` now understands dishes, ingredients and goals."""
    recipes = recipe_repo.load_recipes(conn, user.id)
    if not q.strip():
        return [recipe_summary(r) for r in recipes if matcher.eligible(r, meal_type, diet, max_minutes)]
    outcome = recipe_search.search(recipes, q, meal_type=meal_type, diet=diet, max_minutes=max_minutes)
    return [recipe_summary(r) for r, _ in outcome.hits]


@router.get("/search")
def search_recipes(
    user: CurrentUser,
    conn: Conn,
    today: Today,
    q: str = Query("", max_length=120, description="Dish, ingredient(s), cuisine or goal, e.g. 'high protein breakfast'"),
    meal_type: str | None = Query(None, pattern="^(breakfast|lunch|dinner|snack)$"),
    diet: str | None = Query(None, pattern="^(vegetarian|vegan|gluten_free)$"),
    max_minutes: int | None = Query(None, ge=1, le=600),
    max_kcal: float | None = Query(None, ge=0, le=5000, description="per serving"),
    min_protein: float | None = Query(None, ge=0, le=300, description="grams per serving"),
    min_coverage: float = Query(0.0, ge=0, le=1, description="pantry coverage, 0..1"),
    sort: str = Query("relevance", pattern="^(relevance|time|calories|protein|pantry)$"),
    limit: int = Query(12, ge=1, le=50),
    offset: int = Query(0, ge=0),
    include_external: bool = False,
) -> dict:
    """Search the local catalog; every result carries its pantry match. Nothing unrelated is returned.

    With ``include_external=true`` TheMealDB is searched too. Those results are listed separately, labelled
    with their source, and are never mixed into the local ranking.
    """
    recipes = recipe_repo.load_recipes(conn, user.id)
    outcome = recipe_search.search(recipes, q, meal_type=meal_type, diet=diet, max_minutes=max_minutes,
                                   max_kcal=max_kcal, min_protein=min_protein)
    stock = pantry_repo.load_stock(conn, user.id)

    def decorate(pair):
        recipe, relevance = pair
        m = matcher.evaluate(recipe, stock, today, user.household_size)
        return relevance, m

    rows = [(rel, m) for rel, m in map(decorate, outcome.hits) if m.coverage >= min_coverage]
    pq = outcome.query
    rows.sort(key=lambda t: recipe_search.sort_key(sort, pq, t[0], t[1].recipe, t[1].coverage, t[1].score))
    total = len(rows)
    page = [dict(match_dict(m), relevance=round(rel, 1)) for rel, m in rows[offset: offset + limit]]

    related = [match_dict(matcher.evaluate(r, stock, today, user.household_size)) for r, _ in outcome.related]
    result = {
        "query": q, "total": total, "limit": limit, "offset": offset, "sort": sort,
        "interpreted": {"terms": pq.terms, "meal_type": pq.meal_type, "diet": pq.diet, "max_minutes": pq.max_minutes,
                        "max_kcal": pq.max_kcal, "min_protein": pq.min_protein, "notes": pq.notes},
        "results": page,
        "related": related if total == 0 else [],
        "suggestions": outcome.suggestions if total == 0 else [],
        "nutrition_note": ("Nutrition limits only include recipes whose ingredients all have nutrition data."
                           if pq.has_nutrition_filter() else None),
        "external": [], "external_error": None,
    }
    if include_external and q.strip():
        term = " ".join(pq.terms) or q.strip()
        try:
            result["external"] = [
                {"external_id": m.get("idMeal"), "title": m.get("strMeal"), "category": m.get("strCategory"),
                 "area": m.get("strArea"), "image_url": m.get("strMealThumb"), "source": "TheMealDB"}
                for m in themealdb.search_meals(term)[:8]
            ]
        except themealdb.ExternalApiError as exc:
            result["external_error"] = str(exc)  # reported, never replaced by invented results
    return result


# NOTE: fixed paths ("/suggestions", "/import") must be declared before "/{recipe_id}".
@router.get("/suggestions")
def what_can_i_cook(
    user: CurrentUser,
    conn: Conn,
    today: Today,
    meal_type: str | None = Query(None, pattern="^(breakfast|lunch|dinner|snack)$"),
    max_minutes: int | None = Query(None, ge=1, le=600),
    only_cookable: bool = False,
    min_coverage: float = Query(0.0, ge=0, le=1, description="hide recipes that use less of your pantry than this"),
    status: str | None = Query(None, pattern="^(ready|almost|missing)$"),
    limit: int = Query(10, ge=1, le=50),
) -> list[dict]:
    """Rank recipes by how well they fit your current pantry, favouring food that is about to expire."""
    results = matcher.suggest(
        recipe_repo.load_recipes(conn, user.id),
        pantry_repo.load_stock(conn, user.id),
        today,
        meal_type=meal_type, diet=user.diet, max_minutes=max_minutes,
        servings=user.household_size, only_cookable=only_cookable, min_coverage=min_coverage, limit=50 if status else limit,
    )
    if status:
        results = [m for m in results if m.status == status][:limit]
    return [match_dict(m) for m in results]


@router.post("/import", status_code=201)
def import_from_themealdb(user: CurrentUser, conn: Conn, name: str = Query(..., min_length=2, max_length=60)) -> dict:
    try:
        ids = themealdb.import_by_name(conn, name)
    except themealdb.ExternalApiError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not ids:
        raise HTTPException(404, f"TheMealDB has no meal matching '{name}'")
    return {"imported_recipe_ids": ids}


@router.post("", status_code=201)
def create_recipe(body: RecipeIn, user: CurrentUser, conn: Conn) -> dict:
    if any(m not in MEAL_TYPES for m in body.meal_types):
        raise HTTPException(422, f"meal_types must be from {list(MEAL_TYPES)}")
    with conn:
        items = []
        for i in body.ingredients:
            ing = ingredient_repo.find_or_create(conn, i.name, i.unit)
            items.append((ing.id, to_base(i.amount, i.unit, ing), i.note, i.optional))
        recipe_id = recipe_repo.insert_recipe(
            conn, owner_id=user.id, source="user", title=body.title, description=body.description,
            cuisine=body.cuisine, meal_types=body.meal_types, servings=body.servings,
            prep_min=body.prep_min, cook_min=body.cook_min, difficulty=body.difficulty,
            diet_tags=body.diet_tags, ingredients=items, steps=[s.model_dump() for s in body.steps],
        )
    return recipe_detail(recipe_repo.get_recipe(conn, recipe_id, user.id))  # type: ignore[arg-type]


@router.get("/favorites")
def favorite_recipes(user: CurrentUser, conn: Conn) -> list[dict]:
    """List the current user's favourited recipes with their personal ratings."""
    rows = conn.execute(
        """SELECT r.id, r.title, r.description, r.cuisine, r.meal_types, r.servings, r.prep_min, r.cook_min,
                  r.difficulty, r.diet_tags, r.source, r.image_url, f.rating
           FROM recipe_feedback f JOIN recipes r ON r.id = f.recipe_id
           WHERE f.user_id = ? AND f.is_favorite = 1 ORDER BY f.updated_at DESC, r.title""",
        (user.id,),
    ).fetchall()
    recipes = {r.id: r for r in recipe_repo.load_recipes(conn, user.id, [row["id"] for row in rows])}
    return [{**recipe_summary(recipes[row["id"]]), "rating": row["rating"], "favorite": True} for row in rows if row["id"] in recipes]


@router.put("/{recipe_id}/feedback")
def update_recipe_feedback(recipe_id: int, body: RecipeFeedbackIn, user: CurrentUser, conn: Conn) -> dict:
    """Save a personal favourite flag and/or 1–5 star rating for a recipe."""
    if recipe_repo.get_recipe(conn, recipe_id, user.id) is None:
        raise HTTPException(404, "Recipe not found")
    existing = conn.execute("SELECT is_favorite, rating FROM recipe_feedback WHERE user_id = ? AND recipe_id = ?",
                            (user.id, recipe_id)).fetchone()
    favorite = int(body.favorite if body.favorite is not None else (existing["is_favorite"] if existing else 0))
    rating = body.rating if body.rating is not None else (existing["rating"] if existing else None)
    with conn:
        conn.execute("""INSERT INTO recipe_feedback(user_id, recipe_id, is_favorite, rating, updated_at)
                        VALUES (?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(user_id, recipe_id) DO UPDATE SET is_favorite=excluded.is_favorite,
                        rating=excluded.rating, updated_at=datetime('now')""",
                     (user.id, recipe_id, favorite, rating))
    return {"recipe_id": recipe_id, "favorite": bool(favorite), "rating": rating}


@router.get("/{recipe_id}")
def get_recipe(recipe_id: int, user: CurrentUser, conn: Conn) -> dict:
    recipe = recipe_repo.get_recipe(conn, recipe_id, user.id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    return recipe_detail(recipe)


@router.get("/{recipe_id}/guide")
def cooking_guide(
    recipe_id: int, user: CurrentUser, conn: Conn, today: Today,
    servings: int | None = Query(None, ge=1, le=24),
) -> dict:
    """Step-by-step guide: scaled ingredients, prep list, timed steps, swaps for what you lack."""
    try:
        return guide_dict(recipe_guide(conn, user, recipe_id, servings, today))
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
