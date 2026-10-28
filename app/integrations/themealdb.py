"""TheMealDB integration (free public API, no key needed): import recipes into our catalog.

Design notes
  * The HTTP call is injectable (``fetch``) so tests never touch the network.
  * Imported recipes are idempotent: importing the same meal twice returns the same id.
  * Ingredients we do not know yet are created with ``nutrition_known = 0`` and the
    recipe is flagged ``nutrition_complete = False`` instead of showing wrong numbers.
"""
from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
import urllib.request
from collections.abc import Callable

from ..core.units import UnitError, normalize_unit, to_base
from ..repositories import ingredients as ingredient_repo
from ..repositories import recipes as recipe_repo

BASE_URL = "https://www.themealdb.com/api/json/v1/1"
Fetch = Callable[[str], dict]


class ExternalApiError(RuntimeError):
    """The external API failed or returned something unusable."""


def fetch_json(url: str, timeout: float = 8.0) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - fixed https host
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network errors, bad JSON, timeouts
        raise ExternalApiError(f"TheMealDB request failed: {exc}") from exc


def search_meals(name: str, fetch: Fetch = fetch_json) -> list[dict]:
    data = fetch(f"{BASE_URL}/search.php?s={urllib.parse.quote(name)}")
    return data.get("meals") or []


_FRACTION = r"\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+"
_MEASURE_RE = re.compile(rf"^\s*({_FRACTION})\s*([a-zA-Z]*)")


def _to_number(text: str) -> float:
    total = 0.0
    for part in text.split():
        if "/" in part:
            num, den = part.split("/")
            total += int(num) / int(den)
        else:
            total += float(part)
    return total


def parse_measure(text: str) -> tuple[float, str] | None:
    """'1 1/2 cups' -> (1.5, 'cup'); '200g' -> (200, 'g'); 'to taste' -> None."""
    m = _MEASURE_RE.match(text or "")
    if not m:
        return None
    amount = _to_number(m.group(1))
    unit_text = m.group(2) or "pcs"
    try:
        unit = normalize_unit(unit_text)
    except UnitError:
        unit = "pcs"  # "2 fillets", "3 sprigs": treat as pieces
    return (amount, unit) if amount > 0 else None


def split_steps(instructions: str) -> list[dict]:
    chunks = [c.strip() for c in re.split(r"[\r\n]+", instructions or "") if c.strip()]
    chunks = [c for c in chunks if not re.fullmatch(r"(?i)step\s*\d+\.?", c)]
    if len(chunks) <= 2:  # one big paragraph: split into sentences
        chunks = [s.strip() for s in re.split(r"(?<=[.!?])\s+", " ".join(chunks)) if s.strip()]
    merged: list[str] = []
    for c in chunks:  # glue very short fragments onto the previous step
        if merged and len(c) < 25:
            merged[-1] += " " + c
        else:
            merged.append(c)
    return [{"instruction": c, "duration_min": _minutes_in(c), "tip": None, "passive": False} for c in merged]


def _minutes_in(text: str) -> int | None:
    m = re.search(r"(\d+)(?:\s*(?:-|to)\s*\d+)?\s*(hours?|hrs?|minutes?|mins?)\b", text, re.I)
    if not m:
        return None
    n = int(m.group(1))
    return n * 60 if m.group(2).lower().startswith("h") else n


def _meal_types(category: str) -> list[str]:
    c = (category or "").lower()
    if c == "breakfast":
        return ["breakfast"]
    if c == "dessert":
        return ["snack"]
    if c in ("starter", "side"):
        return ["lunch"]
    return ["lunch", "dinner"]


def _diet_tags(category: str) -> list[str]:
    c = (category or "").lower()
    return ["vegan", "vegetarian"] if c == "vegan" else ["vegetarian"] if c == "vegetarian" else []


def import_meal(conn: sqlite3.Connection, meal: dict) -> int:
    """Store one TheMealDB meal. Returns our recipe id (existing one if already imported)."""
    external_id = str(meal["idMeal"])
    existing = recipe_repo.find_by_external(conn, "themealdb", external_id)
    if existing:
        return existing

    items: list[tuple[int, float, str, bool]] = []
    for n in range(1, 21):
        name = (meal.get(f"strIngredient{n}") or "").strip()
        if not name:
            continue
        raw = (meal.get(f"strMeasure{n}") or "").strip()
        measure = parse_measure(raw)
        ing = ingredient_repo.find_or_create(conn, name, measure[1] if measure else None)
        optional = measure is None  # "to taste", "pinch", "garnish"
        try:
            qty = to_base(measure[0], measure[1], ing) if measure else 1.0
        except UnitError:
            qty, optional = 1.0, True
        items.append((ing.id, qty, raw if measure is None and raw else "", optional))
    if not items:
        raise ExternalApiError("The meal has no ingredients.")

    steps = split_steps(meal.get("strInstructions", ""))
    cook = sum(s["duration_min"] or 0 for s in steps) or 30
    area = (meal.get("strArea") or "other").lower()
    return recipe_repo.insert_recipe(
        conn,
        title=meal["strMeal"].strip(),
        description=f"Imported from TheMealDB ({meal.get('strCategory', 'meal')}).",
        cuisine="other" if area in ("unknown", "") else area,
        meal_types=_meal_types(meal.get("strCategory", "")),
        servings=4,
        prep_min=10,
        cook_min=cook,
        difficulty="medium",
        diet_tags=_diet_tags(meal.get("strCategory", "")),
        source="themealdb",
        external_id=external_id,
        image_url=meal.get("strMealThumb"),
        owner_id=None,
        ingredients=items,
        steps=steps,
    )


def import_by_name(conn: sqlite3.Connection, name: str, fetch: Fetch = fetch_json, limit: int = 3) -> list[int]:
    meals = search_meals(name, fetch)[:limit]
    ids = []
    with conn:
        for meal in meals:
            ids.append(import_meal(conn, meal))
    return ids
