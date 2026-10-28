"""Fitness profiles, nutrition diary, workout log and evidence-backed micronutrients."""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import Conn, CurrentUser, Today
from ..integrations import themealdb
from ..repositories import plans as plan_repo
from ..repositories import recipes as recipe_repo
from ..serializers import recipe_summary

router = APIRouter(tags=["fitness & nutrition"])


class FitnessProfileIn(BaseModel):
    age: int = Field(ge=13, le=100)
    sex: Literal["female", "male", "other"]
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=25, le=350)
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"] = "moderate"
    goal: Literal["fat_loss", "muscle_gain", "maintenance", "general_health"] = "maintenance"
    protein_g_per_kg: float = Field(default=1.6, ge=0.8, le=2.5)


class DiaryIn(BaseModel):
    consumed_on: date | None = None
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] = "snack"
    item_name: str = Field(min_length=1, max_length=120)
    recipe_id: int | None = None
    servings: float = Field(default=1, gt=0, le=50)
    kcal: float = Field(default=0, ge=0, le=20000)
    protein_g: float = Field(default=0, ge=0, le=1000)
    carbs_g: float = Field(default=0, ge=0, le=2000)
    fat_g: float = Field(default=0, ge=0, le=1000)
    micros: dict[str, float] = Field(default_factory=dict)


class WorkoutIn(BaseModel):
    workout_date: date | None = None
    workout_type: str = Field(min_length=2, max_length=80)
    duration_min: int = Field(ge=1, le=1440)
    intensity: Literal["light", "moderate", "vigorous"] = "moderate"
    notes: str = Field(default="", max_length=1000)




USDA_BASE = "https://api.nal.usda.gov/fdc/v1"
NUTRIENT_MAP = {
    "Vitamin C, total ascorbic acid": ("vitamin_c", "mg"),
    "Vitamin A, RAE": ("vitamin_a", "µg RAE"),
    "Calcium, Ca": ("calcium", "mg"),
    "Iron, Fe": ("iron", "mg"),
    "Potassium, K": ("potassium", "mg"),
    "Magnesium, Mg": ("magnesium", "mg"),
    "Sodium, Na": ("sodium", "mg"),
    "Zinc, Zn": ("zinc", "mg"),
    "Folate, total": ("folate", "µg"),
    "Vitamin B-12": ("vitamin_b12", "µg"),
    "Vitamin D (D2 + D3)": ("vitamin_d", "µg"),
    "Phosphorus, P": ("phosphorus", "mg"),
}


def _usda_json(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MealMate-Pro/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310 - fixed USDA HTTPS host
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(502, "USDA FoodData Central request failed. Check connectivity and the API key.") from exc

ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}


def _targets(p: sqlite3.Row) -> dict:
    # Mifflin-St Jeor estimate; other uses midpoint to avoid assuming sex-specific coefficient.
    sex_adjustment = 5 if p["sex"] == "male" else -161 if p["sex"] == "female" else -78
    bmr = 10 * p["weight_kg"] + 6.25 * p["height_cm"] - 5 * p["age"] + sex_adjustment
    maintenance = bmr * ACTIVITY[p["activity_level"]]
    delta = -300 if p["goal"] == "fat_loss" else 250 if p["goal"] == "muscle_gain" else 0
    kcal = round(max(1200, maintenance + delta))
    protein = round(p["weight_kg"] * p["protein_g_per_kg"])
    fat = round((kcal * 0.28) / 9)
    carbs = round(max(0, (kcal - protein * 4 - fat * 9) / 4))
    return {"estimated_bmr_kcal": round(bmr), "maintenance_kcal": round(maintenance), "daily_kcal": kcal,
            "protein_g": protein, "carbs_g": carbs, "fat_g": fat,
            "method": "Mifflin-St Jeor estimate; activity multiplier; goal adjustment",
            "disclaimer": "Planning estimate, not medical advice. Individual needs vary; consult a qualified professional for clinical goals."}


@router.get("/fitness/profile")
def get_fitness_profile(user: CurrentUser, conn: Conn) -> dict:
    row = conn.execute("SELECT * FROM fitness_profiles WHERE user_id=?", (user.id,)).fetchone()
    return {"profile": dict(row) if row else None, "targets": _targets(row) if row else None}


@router.put("/fitness/profile")
def save_fitness_profile(body: FitnessProfileIn, user: CurrentUser, conn: Conn) -> dict:
    values = body.model_dump()
    with conn:
        conn.execute("""INSERT INTO fitness_profiles
          (user_id,age,sex,height_cm,weight_kg,activity_level,goal,protein_g_per_kg,updated_at)
          VALUES (:user_id,:age,:sex,:height_cm,:weight_kg,:activity_level,:goal,:protein_g_per_kg,datetime('now'))
          ON CONFLICT(user_id) DO UPDATE SET age=excluded.age,sex=excluded.sex,height_cm=excluded.height_cm,
          weight_kg=excluded.weight_kg,activity_level=excluded.activity_level,goal=excluded.goal,
          protein_g_per_kg=excluded.protein_g_per_kg,updated_at=datetime('now')""", {"user_id": user.id, **values})
    row = conn.execute("SELECT * FROM fitness_profiles WHERE user_id=?", (user.id,)).fetchone()
    targets = _targets(row)
    conn.execute("UPDATE users SET daily_kcal=? WHERE id=?", (targets["daily_kcal"], user.id))
    conn.commit()
    return {"profile": dict(row), "targets": targets}


def _recipe_micronutrients(conn: sqlite3.Connection, recipe_id: int, servings: float = 1.0) -> dict:
    rows = conn.execute("""SELECT i.name,ri.quantity,i.base_unit,i.density_g_per_ml,i.grams_per_piece,
      r.servings AS recipe_servings,n.nutrient_key,n.amount_per_100g,n.unit,n.source_name,n.source_id
      FROM recipe_ingredients ri JOIN ingredients i ON i.id=ri.ingredient_id
      JOIN recipes r ON r.id=ri.recipe_id JOIN ingredient_nutrients n ON n.ingredient_id=i.id
      WHERE ri.recipe_id=? AND ri.optional=0""", (recipe_id,)).fetchall()
    values: dict[str, float] = {}
    sources: list[dict] = []
    for row in rows:
        grams = (float(row["quantity"]) if row["base_unit"] == "g" else
                 float(row["quantity"]) * float(row["density_g_per_ml"] or 1) if row["base_unit"] == "ml" else
                 float(row["quantity"]) * float(row["grams_per_piece"] or 1))
        key = row["nutrient_key"]
        values[key] = values.get(key, 0.0) + float(row["amount_per_100g"]) * grams / 100.0 / max(row["recipe_servings"], 1) * servings
        source = {"ingredient": row["name"], "source": row["source_name"], "source_id": row["source_id"], "nutrient": key, "unit": row["unit"]}
        if source not in sources: sources.append(source)
    return {"values": {k: round(v, 4) for k, v in values.items()}, "sources": sources}


@router.post("/diary", status_code=201)
def add_diary_entry(body: DiaryIn, user: CurrentUser, conn: Conn, today: Today) -> dict:
    values = body.model_dump()
    day = values.pop("consumed_on") or today
    micros = values.pop("micros")
    recipe_id = values.get("recipe_id")
    source = "manual"
    if recipe_id is not None:
        recipe = recipe_repo.get_recipe(conn, recipe_id, user.id)
        if recipe is None:
            raise HTTPException(404, "Recipe not found")
        n = recipe.nutrition_per_serving
        values["item_name"] = recipe.title
        values["kcal"], values["protein_g"], values["carbs_g"], values["fat_g"] = n.kcal, n.protein, n.carbs, n.fat
        micros = _recipe_micronutrients(conn, recipe_id, values["servings"])
        source = "recipe"
    if not isinstance(micros, dict) or "values" not in micros:
        micros = {"values": micros, "sources": []}
    with conn:
        cur = conn.execute("""INSERT INTO food_diary
          (user_id,consumed_on,meal_type,item_name,recipe_id,servings,kcal,protein_g,carbs_g,fat_g,micros_json,source)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
          (user.id, day.isoformat(), values["meal_type"], values["item_name"], recipe_id, values["servings"],
           values["kcal"] * values["servings"], values["protein_g"] * values["servings"],
           values["carbs_g"] * values["servings"], values["fat_g"] * values["servings"], json.dumps(micros), source))
    row = conn.execute("SELECT * FROM food_diary WHERE id=?", (cur.lastrowid,)).fetchone()
    result = dict(row); result["micros"] = json.loads(result.pop("micros_json"))
    return result


@router.get("/diary")
def list_diary(user: CurrentUser, conn: Conn, today: Today, day: date = Query(default=None)) -> list[dict]:
    rows = conn.execute("SELECT * FROM food_diary WHERE user_id=? AND consumed_on=? ORDER BY created_at,id", (user.id, (day or today).isoformat()))
    output = []
    for row in rows:
        item = dict(row); item["micros"] = json.loads(item.pop("micros_json")); output.append(item)
    return output


@router.delete("/diary/{entry_id}")
def delete_diary_entry(entry_id: int, user: CurrentUser, conn: Conn) -> dict:
    with conn:
        cur = conn.execute("DELETE FROM food_diary WHERE id=? AND user_id=?", (entry_id, user.id))
    if not cur.rowcount:
        raise HTTPException(404, "Food diary entry not found")
    return {"deleted": True, "id": entry_id}


@router.get("/nutrition/daily")
def daily_nutrition(user: CurrentUser, conn: Conn, today: Today, day: date = Query(default=None)) -> dict:
    selected = (day or today).isoformat()
    actual = conn.execute("""SELECT COUNT(*) entries,COALESCE(SUM(kcal),0) kcal,COALESCE(SUM(protein_g),0) protein_g,
        COALESCE(SUM(carbs_g),0) carbs_g,COALESCE(SUM(fat_g),0) fat_g FROM food_diary WHERE user_id=? AND consumed_on=?""", (user.id, selected)).fetchone()
    planned_rows = plan_repo.meals_on(conn, user.id, date.fromisoformat(selected))  # newest plan wins per meal slot
    recipes = {r.id: r for r in recipe_repo.load_recipes(conn, user.id)}
    planned_totals = {"entries": len(planned_rows), "kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    planned_complete = True
    for item in planned_rows:
        recipe = recipes.get(item["recipe_id"])
        if recipe is None:
            planned_complete = False
            continue
        # per person: one serving of each planned meal (the plan's "servings" is how many portions get cooked)
        nutrition = recipe.nutrition_per_serving
        planned_totals["kcal"] += nutrition.kcal
        planned_totals["protein_g"] += nutrition.protein
        planned_totals["carbs_g"] += nutrition.carbs
        planned_totals["fat_g"] += nutrition.fat
        planned_complete = planned_complete and recipe.nutrition_complete
    planned = planned_totals
    micro_rows = conn.execute("SELECT micros_json FROM food_diary WHERE user_id=? AND consumed_on=?", (user.id, selected)).fetchall()
    micronutrients: dict[str, float] = {}
    micro_sources: list[dict] = []
    for micro_row in micro_rows:
        try:
            record = json.loads(micro_row["micros_json"] or "{}")
        except json.JSONDecodeError:
            continue
        for key, amount in record.get("values", {}).items():
            if isinstance(amount, (int, float)):
                micronutrients[key] = micronutrients.get(key, 0.0) + float(amount)
        for source in record.get("sources", []):
            if source not in micro_sources:
                micro_sources.append(source)
    profile = conn.execute("SELECT * FROM fitness_profiles WHERE user_id=?", (user.id,)).fetchone()
    targets = _targets(profile) if profile else ({"daily_kcal": user.daily_kcal} if user.daily_kcal else None)
    def clean(row): return {k: round(row[k] or 0, 1) if k != "entries" else row[k] for k in row.keys()}
    return {"date": selected, "planned": clean(planned), "planned_nutrition_complete": planned_complete, "consumed": clean(actual), "consumed_micronutrients": {k: round(v, 3) for k, v in micronutrients.items()}, "micronutrient_sources": micro_sources, "targets": targets,
            "note": "Planned meals and consumed diary entries are separate. Unknown ingredient micronutrients are not estimated."}


@router.post("/workouts", status_code=201)
def add_workout(body: WorkoutIn, user: CurrentUser, conn: Conn, today: Today) -> dict:
    day = body.workout_date or today
    with conn:
        cur = conn.execute("INSERT INTO workouts(user_id,workout_date,workout_type,duration_min,intensity,notes) VALUES(?,?,?,?,?,?)",
          (user.id, day.isoformat(), body.workout_type.strip(), body.duration_min, body.intensity, body.notes))
    return dict(conn.execute("SELECT * FROM workouts WHERE id=?", (cur.lastrowid,)).fetchone())


@router.get("/workouts")
def list_workouts(user: CurrentUser, conn: Conn, day: date | None = None, limit: int = Query(30, ge=1, le=200)) -> list[dict]:
    if day:
        rows = conn.execute("SELECT * FROM workouts WHERE user_id=? AND workout_date=? ORDER BY id DESC", (user.id, day.isoformat()))
    else:
        rows = conn.execute("SELECT * FROM workouts WHERE user_id=? ORDER BY workout_date DESC,id DESC LIMIT ?", (user.id, limit))
    return [dict(r) for r in rows]


@router.delete("/workouts/{workout_id}")
def delete_workout(workout_id: int, user: CurrentUser, conn: Conn) -> dict:
    with conn:
        cur = conn.execute("DELETE FROM workouts WHERE id=? AND user_id=?", (workout_id, user.id))
    if not cur.rowcount: raise HTTPException(404, "Workout not found")
    return {"deleted": True, "id": workout_id}


@router.get("/recipes/discover")
def discover_recipes(q: str = Query(min_length=1, max_length=80), limit: int = Query(10, ge=1, le=25)) -> list[dict]:
    """Search TheMealDB without requiring an import first; returns source-attributed results."""
    try:
        meals = themealdb.search_meals(q)[:limit]
    except themealdb.ExternalApiError as exc:
        raise HTTPException(502, str(exc)) from exc
    return [{"external_id": m.get("idMeal"), "title": m.get("strMeal"), "image_url": m.get("strMealThumb"),
             "category": m.get("strCategory"), "area": m.get("strArea"), "source": "TheMealDB",
             "source_url": m.get("strSource") or m.get("strYoutube"), "can_import": True} for m in meals]


@router.get("/nutrition/ingredients/{ingredient_id}/micronutrients")
def ingredient_micronutrients(ingredient_id: int, user: CurrentUser, conn: Conn) -> dict:
    ing = conn.execute("SELECT id,name FROM ingredients WHERE id=?", (ingredient_id,)).fetchone()
    if not ing: raise HTTPException(404, "Ingredient not found")
    rows = conn.execute("SELECT nutrient_key,amount_per_100g,unit,source_name,source_id FROM ingredient_nutrients WHERE ingredient_id=? ORDER BY nutrient_key", (ingredient_id,))
    facts = [dict(r) for r in rows]
    return {"ingredient": ing["name"], "basis": "per 100 g", "micronutrients": facts,
            "data_available": bool(facts), "message": None if facts else "No verified micronutrient facts are stored for this ingredient yet."}


@router.get("/nutrition/search-foods")
def search_verified_foods(user: CurrentUser, q: str = Query(min_length=2, max_length=100), limit: int = Query(8, ge=1, le=25)) -> dict:
    """Search USDA FoodData Central; requires a USDA_FDC_API_KEY environment variable."""
    key = os.getenv("USDA_FDC_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Set USDA_FDC_API_KEY to enable verified USDA FoodData Central lookups.")
    query = urllib.parse.urlencode({"api_key": key, "query": q, "pageSize": limit, "dataType": "Foundation,SR Legacy"})
    data = _usda_json(f"{USDA_BASE}/foods/search?{query}")
    return {"source": "USDA FoodData Central", "foods": [
        {"fdc_id": f.get("fdcId"), "description": f.get("description"), "data_type": f.get("dataType"),
         "brand_owner": f.get("brandOwner"), "published_date": f.get("publicationDate")}
        for f in data.get("foods", [])]}


@router.post("/nutrition/ingredients/{ingredient_id}/import-usda/{fdc_id}")
def import_usda_nutrients(ingredient_id: int, fdc_id: int, user: CurrentUser, conn: Conn) -> dict:
    """Attach USDA nutrient facts to an existing ingredient, preserving source IDs."""
    key = os.getenv("USDA_FDC_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Set USDA_FDC_API_KEY to enable USDA imports.")
    ing = conn.execute("SELECT id,name FROM ingredients WHERE id=?", (ingredient_id,)).fetchone()
    if not ing:
        raise HTTPException(404, "Ingredient not found")
    data = _usda_json(f"{USDA_BASE}/food/{fdc_id}?api_key={urllib.parse.quote(key)}")
    facts = []
    for item in data.get("foodNutrients", []):
        nutrient = item.get("nutrient", {})
        name = nutrient.get("name") or item.get("nutrientName")
        if name not in NUTRIENT_MAP:
            continue
        key_name, unit = NUTRIENT_MAP[name]
        amount = item.get("amount", item.get("value"))
        if amount is not None and float(amount) >= 0:
            facts.append((ingredient_id, key_name, float(amount), unit, "USDA FoodData Central", str(fdc_id)))
    if not facts:
        raise HTTPException(422, "USDA record did not contain supported micronutrients.")
    with conn:
        conn.executemany("""INSERT INTO ingredient_nutrients(ingredient_id,nutrient_key,amount_per_100g,unit,source_name,source_id)
          VALUES(?,?,?,?,?,?) ON CONFLICT(ingredient_id,nutrient_key) DO UPDATE SET
          amount_per_100g=excluded.amount_per_100g,unit=excluded.unit,source_name=excluded.source_name,source_id=excluded.source_id""", facts)
    return {"ingredient": ing["name"], "fdc_id": fdc_id, "source": "USDA FoodData Central", "basis": "per 100 g", "facts_imported": len(facts)}


@router.get("/nutrition/recipes/{recipe_id}/micronutrients")
def recipe_micronutrients(recipe_id: int, user: CurrentUser, conn: Conn) -> dict:
    recipe = recipe_repo.get_recipe(conn, recipe_id, user.id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    rows = conn.execute("""SELECT i.id AS ingredient_id,i.name,ri.quantity,i.base_unit,i.density_g_per_ml,i.grams_per_piece,n.nutrient_key,n.amount_per_100g,n.unit,n.source_name,n.source_id
      FROM recipe_ingredients ri JOIN ingredients i ON i.id=ri.ingredient_id
      JOIN ingredient_nutrients n ON n.ingredient_id=i.id WHERE ri.recipe_id=? AND ri.optional=0""", (recipe_id,))
    totals: dict[str, dict] = {}
    for row in rows:
        # FoodData Central values are per 100 g; recipe quantity is converted to grams using ingredient density.
        grams = (float(row["quantity"]) if row["base_unit"] == "g" else
                 float(row["quantity"]) * float(row["density_g_per_ml"] or 1) if row["base_unit"] == "ml" else
                 float(row["quantity"]) * float(row["grams_per_piece"] or 1))
        key = row["nutrient_key"]
        target = totals.setdefault(key, {"nutrient": key, "amount": 0.0, "unit": row["unit"], "sources": []})
        target["amount"] += float(row["amount_per_100g"]) * grams / 100.0 / recipe.servings
        source = {"name": row["source_name"], "id": row["source_id"], "ingredient": row["name"]}
        if source not in target["sources"]: target["sources"].append(source)
    return {"recipe_id": recipe_id, "title": recipe.title, "basis": "per serving", "micronutrients":
            [{**v, "amount": round(v["amount"], 3)} for v in totals.values()],
            "data_complete": bool(totals), "note": "Only nutrients linked to a source-attributed USDA record are included; missing values are not treated as zero."}


@router.get("/workout-fuel/recommendations")
def workout_fuel_recommendations(user: CurrentUser, conn: Conn, phase: Literal["pre", "post"] = "pre", limit: int = Query(6, ge=1, le=20)) -> dict:
    """Rank locally available recipes for general pre/post-workout meal ideas."""
    recipes = recipe_repo.load_recipes(conn, user.id)
    if phase == "pre":
        ranked = sorted(recipes, key=lambda r: (r.nutrition_per_serving.carbs, r.nutrition_per_serving.kcal), reverse=True)
        guidance = "Consider a familiar carbohydrate-containing meal 1–3 hours before training, adjusted to portion size and tolerance."
    else:
        ranked = sorted(recipes, key=lambda r: (r.nutrition_per_serving.protein, r.nutrition_per_serving.carbs), reverse=True)
        guidance = "Choose a meal with protein and carbohydrates; overall daily intake and consistency matter most for recovery."
    return {"phase": phase, "guidance": guidance, "recipes": [
        {**recipe_summary(r), "nutrition_complete": r.nutrition_complete} for r in ranked[:limit]],
        "disclaimer": "General ideas, not individualized sports nutrition or medical advice."}


@router.get("/recipes/{recipe_id}/workout-fuel")
def workout_fuel(recipe_id: int, user: CurrentUser, conn: Conn, phase: Literal["pre", "post"] = "pre") -> dict:
    recipe = recipe_repo.get_recipe(conn, recipe_id, user.id)
    if recipe is None: raise HTTPException(404, "Recipe not found")
    n = recipe.nutrition_per_serving
    if phase == "pre":
        guidance = "Choose a familiar meal with easily tolerated carbohydrates; allow roughly 1–3 hours before training based on portion size and comfort."
        fit = "carbohydrate-supportive" if n.carbs >= n.protein else "general"
    else:
        guidance = "A meal containing protein and carbohydrates can support recovery; daily total intake and consistency matter most."
        fit = "protein-containing" if n.protein >= 15 else "general"
    return {"recipe": recipe_summary(recipe), "phase": phase, "fit": fit, "guidance": guidance,
            "nutrition_per_serving": n.as_dict(), "nutrition_complete": recipe.nutrition_complete,
            "disclaimer": "General food-planning guidance, not medical or sports-dietitian advice."}
