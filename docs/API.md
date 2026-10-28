# API reference

Base URL (local): `http://localhost:8000`. Interactive docs: `/docs` (Swagger UI) and `/redoc`.
Every endpoint except `/health`, `/auth/register` and `/auth/login` needs the header `Authorization: Bearer <token>`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/auth/register` | Create an account |
| POST | `/auth/login` | Get a JWT |
| GET / PUT | `/me` | Read / update profile (calorie target, diet, household size) |
| GET | `/dashboard` | **All overview numbers in one response** (pantry counts, ready/almost-ready recipes, today's plan, planned vs eaten) |
| GET | `/pantry` | Totals per ingredient (SQL `GROUP BY`), items expiring within 3 days, and `expired` items |
| GET | `/pantry/batches` | Batches that still have stock: remaining amount (`display`), `days_left`, `status` (ok / expiring / expired / no_expiry) |
| POST | `/pantry` | Add a batch. Typed names are matched to the catalog (`matched_as`); unknown ones return `created_new: true` and `similar` hints |
| PATCH | `/pantry/{id}` | Correct the remaining amount / expiry of a batch (`amount: 0` marks it used up) |
| DELETE | `/pantry/{id}` | Remove a batch |
| GET | `/pantry/ingredients/search?q=` | Look up ingredient names |
| GET | `/recipes` | List and filter (`q`, `meal_type`, `diet`, `max_minutes`); `q` understands dishes, ingredients and goals |
| GET | `/recipes/search` | Full search: relevance, pantry match, `sort`, `limit`/`offset`, nutrition limits, optional `include_external=true` (TheMealDB, listed separately) |
| GET | `/recipes/suggestions` | "What can I cook now?" ranked by your pantry. Extras: `min_coverage`, `status=ready\|almost\|missing`; each item has `status`, `substitutions` |
| GET | `/recipes/favorites` | Current user's favourite recipes with personal ratings |
| PUT | `/recipes/{recipe_id}/feedback` | Save `favorite` (boolean) and/or `rating` (1–5) for a recipe |
| POST | `/recipes` | Create your own (private) recipe |
| POST | `/recipes/import?name=` | Import from TheMealDB |
| GET | `/recipes/{id}` | Recipe detail |
| GET | `/recipes/{id}/guide?servings=` | Step-by-step cooking guide |
| POST | `/plans/generate` | Build a daily or weekly plan |
| GET | `/plans` | Your saved plans |
| GET | `/plans/stats` | Most-cooked recipes (aggregation) |
| GET | `/plans/{id}` | A saved plan with cooked flags |
| GET | `/plans/{id}/grocery` | Shopping list for the meals not cooked yet, vs today's pantry |
| POST | `/plans/{id}/meals/{meal_id}/cook` | Mark cooked and deduct ingredients |
| PUT | `/plans/{id}/meals/{meal_id}` | Swap the recipe (and optionally servings) of an uncooked meal |
| DELETE | `/plans/{id}` | Delete a saved plan (pantry untouched) |

## Status codes

| Code | When |
|---|---|
| 201 | Created (register, pantry add, recipe, plan). `POST /plans/generate` returns `saved: true` only after the plan was read back from the database |
| 401 | Missing, invalid or expired token; wrong email or password |
| 404 | Not found, **or belongs to another user** (we never reveal that it exists) |
| 409 | Duplicate email; meal already cooked; cannot cook because ingredients are missing |
| 422 | Invalid input: bad unit, `days` outside 1-14, unknown meal type, short password |
| 502 | TheMealDB is unreachable |

## Examples

### Add to the pantry

Units may be `g, kg, ml, l, tsp, tbsp, cup, pcs` (plus words such as `cloves` or `slices`). If `unit` is omitted
the ingredient's base unit is used.

```http
POST /pantry
{ "ingredient": "red lentils", "amount": 1, "unit": "cup", "expires_on": "2026-12-01" }
```
```json
{ "id": 2, "ingredient": "red lentils", "quantity": 204.0, "unit": "g" }
```
`1 cup` of lentils was converted to grams once, here, using the ingredient's density.

An ingredient the catalog does not know (for example "dragon fruit") is created automatically, with
`nutrition_known = false`.

### Generate a plan

```http
POST /plans/generate
{
  "start_date": "2026-10-26",
  "days": 7,
  "meals": ["breakfast", "lunch", "dinner"],
  "servings": 2,
  "daily_kcal": 2000,
  "diet": null,
  "exclude_recipe_ids": [],
  "max_repeats": 2,
  "save": true
}
```

`days: 1` is a daily plan, `days: 7` a weekly plan (max 14). `servings` is how many portions you cook per meal and
defaults to your household size. Calories and macros in the response are **per person**.

Response (trimmed):

```json
{
  "plan_id": 1,
  "start_date": "2026-10-26",
  "days": [
    {
      "date": "2026-10-26",
      "meals": [
        {
          "meal_type": "lunch",
          "recipe_id": 8,
          "title": "Chickpea Spinach Curry",
          "servings": 2,
          "total_min": 35,
          "coverage_pct": 100,
          "missing": [],
          "uses_expiring": ["spinach"],
          "why": ["You have 5 of 5 key ingredients.", "Uses spinach, which expires in 1 day."],
          "nutrition_per_serving": { "kcal": 326, "protein_g": 16.0, "...": "..." }
        }
      ],
      "nutrition": { "totals": { "kcal": 1520, "...": "..." }, "percent_of_target": 76, "macro_split": { "...": "..." } }
    }
  ],
  "average_daily_nutrition": { "...": "..." },
  "grocery_list": [
    { "name": "spinach", "category": "produce", "quantity": 100.0, "unit": "g", "display": "100 g" }
  ],
  "warnings": [
    "The plan averages 1520 kcal per day, 24% below your 2000 kcal target. Add 'snack' to the meals list to close the gap."
  ]
}
```

`warnings` is how the planner stays honest: calorie gaps, repeated recipes because few match your filters,
and pantry food that will expire without being used.

### Cooking guide

```http
GET /recipes/8/guide?servings=4
```
```json
{
  "title": "Chickpea Spinach Curry",
  "servings": 4,
  "can_cook_now": false,
  "missing": ["spinach"],
  "ingredients": [
    { "name": "chickpeas", "quantity": "533 g", "note": "drained and rinsed", "optional": false, "status": "in_pantry" },
    { "name": "spinach", "quantity": "200 g", "note": "roughly chopped", "optional": false, "status": "missing" },
    { "name": "salt", "quantity": "8 g", "note": "", "optional": false, "status": "staple" }
  ],
  "mise_en_place": [
    "Read the whole recipe once, then put every ingredient and a clean board and knife within reach.",
    "Chickpeas (533 g): drained and rinsed."
  ],
  "steps": [
    {
      "number": 1,
      "instruction": "Heat the oil in a wide pot over medium heat. Add the onion and cook for 6 minutes ...",
      "duration_min": 6,
      "tip": "Patience here builds the sweet base of the curry. Do not rush it on high heat.",
      "passive": false,
      "starts_at_min": 0
    }
  ],
  "substitutions": { "spinach": ["Any leafy green: kale, chard, or fenugreek leaves", "Frozen spinach, half the weight"] }
}
```

`status` is one of `in_pantry`, `partial`, `missing`, `staple`. `starts_at_min` is an approximate running clock.
`passive: true` marks steps (simmering, baking) where your hands are free.

### Cook a planned meal

```http
POST /plans/1/meals/3/cook
```
```json
{ "meal_id": 3, "cooked": true, "recipe": "Red Lentil Soup", "pantry_rows_updated": 5 }
```
If an ingredient is missing nothing changes and you get `409` with `"Missing ingredients: ..."`.

## Fitness, food diary and micronutrients

All endpoints below except the optional external lookup require a bearer token.

- `GET /fitness/profile` — return the saved fitness profile and calculated targets.
- `PUT /fitness/profile` — save age, sex, height, weight, activity level, goal (`fat_loss`, `muscle_gain`, `maintenance`, `general_health`) and protein g/kg.
- `POST /diary` / `GET /diary` / `DELETE /diary/{entry_id}` — create, list and remove actual food-consumption entries. Entries can be manually entered or linked to a recipe using `recipe_id`.
- `GET /nutrition/daily?day=YYYY-MM-DD` — compare planned meal nutrition with consumed diary totals; sourced micronutrient totals are returned when available.
- `POST /workouts` / `GET /workouts` / `DELETE /workouts/{workout_id}` — log and review workouts.
- `GET /workout-fuel/recommendations?phase=pre|post` — general recipe ideas ranked for carbohydrate support (pre) or protein/carbohydrate support (post).
- `GET /recipes/{recipe_id}/workout-fuel?phase=pre|post` — nutrition and general timing guidance for a specific recipe.
- `GET /recipes/discover?q=...` — live TheMealDB recipe search from the web UI.
- `GET /nutrition/search-foods?q=...` — search USDA FoodData Central; requires `USDA_FDC_API_KEY`.
- `POST /nutrition/ingredients/{ingredient_id}/import-usda/{fdc_id}` — import supported vitamin/mineral facts from a USDA record, retaining source name and FDC ID.
- `GET /nutrition/ingredients/{ingredient_id}/micronutrients` and `GET /nutrition/recipes/{recipe_id}/micronutrients` — inspect available source-attributed micronutrient facts.

### Nutrition interpretation

Energy and macro targets are estimates based on the Mifflin–St Jeor equation, an activity multiplier and a modest goal adjustment. They are planning estimates, not medical advice. Micronutrient facts are only included when an ingredient is linked to a supported USDA FoodData Central record; missing values are not treated as zero. Recipe imports from TheMealDB do not automatically imply complete nutrient data.

## Search query language (`/recipes/search?q=`)

The text is split into **filters** and **search terms**. Every term must match a recipe's title, ingredients, cuisine or description; unrelated recipes are never returned.

| You type | Understood as |
|---|---|
| `paneer`, `eggs and spinach` | ingredient terms (all must match) |
| `chick` | partial word (prefix match) |
| `high protein breakfast` | meal type breakfast, protein >= 25 g per serving |
| `meals with at least 40 grams of protein` | protein >= 40 g per serving |
| `recipes under 500 calories`, `low calorie dinner` | <= 500 / <= 450 kcal per serving |
| `quick meals under 20 minutes` | total time <= 20 min |
| `vegetarian`, `vegan`, `gluten free` | diet filter |
| `Indian meals for muscle gain` | cuisine term `indian` + protein >= 25 g |

The response's `interpreted` block shows how the query was read. With no match, `results` is empty and `related` / `suggestions` explain what is available. Nutrition limits only consider recipes whose ingredients all have nutrition data.
