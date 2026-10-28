# Build guide: how we made MealMate Pro from scratch

This guide explains **what we built, in what order, and why**, in plain language, with small examples you can run.
If you can follow it, you can explain every line of this project in an interview.

---

## 0. The idea

**Problem.** People buy food, forget it, and throw it away. Meal planners start from *recipes*; they do not know
what is already in your kitchen.

**Our twist.** Start from the **pantry**. The app answers three questions:

1. *What can I cook right now?*
2. *What should I eat this week, and what do I really need to buy?*
3. *How exactly do I cook it?*

**Why it is different from your other projects.** SpendSmart is about money, and HabitForge is about one streak
algorithm. MealMate Pro shows other skills: a many-to-many data model, unit conversion, an expiry-aware inventory,
a planning algorithm, an external API and a different stack (Python/FastAPI).

---

## 1. Plan before you code

Write the features as sentences from the user's point of view. Each sentence becomes an endpoint and a test.

| As a user I can... | Becomes |
|---|---|
| tell the app what I have, and when it expires | `POST /pantry` |
| see what I can cook now | `GET /recipes/suggestions` |
| get a plan for a day or a week | `POST /plans/generate` |
| get a shopping list with only what I miss | `grocery_list` in the plan |
| follow a recipe step by step | `GET /recipes/{id}/guide` |
| say "I cooked it" and have the pantry update | `POST /plans/{id}/meals/{id}/cook` |

**Rule of thumb:** build the *brain* first (pure logic), then storage, then the web layer. We did it in that order.

---

## 2. Project setup

```bash
mkdir mealmate-pro && cd mealmate-pro
git init
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install fastapi "uvicorn[standard]" pydantic PyJWT python-dotenv
pip install pytest httpx ruff
pip freeze    # then write the versions you need into requirements.txt / requirements-dev.txt
```

Create the folders. The names matter, because each folder has **one job**:

```
app/core/          the brain (pure Python)
app/repositories/  SQL only
app/routers/       HTTP only
app/seed/          starter data
tests/             proof it works
docs/              explanation
```

---

## 3. Design the data first

### 3.1 The tables

`users`, `ingredients`, `recipes`, `recipe_ingredients`, `recipe_steps`, `pantry_items`, `meal_plans`, `planned_meals`.
Full SQL: `app/schema.sql`.

### 3.2 The many-to-many relationship (a classic interview topic)

*A recipe uses many ingredients. An ingredient is used by many recipes.* You cannot store that in one column, so you
add a **junction table**:

```
(ids below are illustrative)
recipes                     recipe_ingredients                      ingredients
id | title                  recipe_id | ingredient_id | quantity    id | name
8  | Chickpea Curry         8         | 28            | 400         28 | chickpeas
9  | Red Lentil Soup        8         | 3             | 150         3  | spinach
                            9         | 3             | ...
```

The junction row also stores data about the *relationship*: how much, which preparation note, whether it is optional.
`PRIMARY KEY (recipe_id, ingredient_id)` stops the same ingredient being listed twice for one recipe.

### 3.3 Two decisions that made everything simpler

**Decision 1: store every quantity in a base unit (g, ml or pcs).**
Humans write "2 tbsp", "1 cup", "3 cloves". If you keep those, every calculation needs to know about units. Instead
we convert **once, when data comes in** (`app/core/units.py`), and use plain numbers everywhere else.

```python
to_base(2, "tbsp", olive_oil)      # -> 30.0   (ml)
to_base(1, "cup",  rice)           # -> 204.0  (g, because 1 cup = 240 ml and rice is 0.85 g/ml)
to_base(100, "g",  onion)          # -> 0.91   (pcs, because one onion is about 110 g)
to_base(2, "pcs",  milk)           # -> UnitError (we do not know how much a "piece" of milk weighs)
```

Refusing to guess (`UnitError`) is deliberate. A wrong conversion silently gives wrong shopping lists.

**Decision 2: the pantry stores batches, not totals.**
If you buy 6 eggs on Monday and 6 on Friday, they expire on different days. One row per purchase keeps that.

```
pantry_items:  spinach 100 g  expires Oct 30
               spinach 100 g  expires Oct 26
```

---

## 4. First-expiring-first-out (`core/stock.py`)

When you cook, use the batch that expires first. This is how shops handle stock too (FEFO).

Example: you need 150 g spinach. Batch A has 100 g expiring in 5 days, batch B has 100 g expiring tomorrow.

```
take 100 g from B (expires first)   -> B is empty
take  50 g from A                   -> A has 50 g left
```

Two more rules, both covered by tests:
* a batch that has expired **before the day you cook** cannot be used (a batch is still fine on its last day);
* anything the pantry cannot cover is returned as a **shortfall**. Remember that word, it becomes the shopping list.

---

## 5. "What can I cook?" (`core/matcher.py`)

For each recipe we compute two numbers.

**Coverage** = how much of the recipe you can already make, from 0 to 1.
For each needed ingredient: `min(have / need, 1)`. Then take the average. Staples (salt, oil, spices) and optional
ingredients are ignored.

**Urgency** = does it help use up food that will soon go bad? An ingredient expiring in *d* days adds `1 / (1 + d)`.
Today counts 1, tomorrow 0.5, in two days 0.33. The sum is divided by 2 and capped at 1.

```
score = 100 × (0.7 × coverage + 0.3 × urgency)
```

### Worked example

Recipe: **Chickpea Spinach Curry** (3 servings). You have 400 g chickpeas, 40 g spinach (expires tomorrow),
1 onion and 3 garlic cloves. You have no canned tomatoes.

| Ingredient | Need | Have | Ratio |
|---|---|---|---|
| chickpeas | 400 g | 400 g | 1.00 |
| spinach | 150 g | 40 g | 0.27 |
| onion | 1 | 1 | 1.00 |
| garlic | 3 | 3 | 1.00 |
| canned tomatoes | 400 g | 0 | 0.00 |

* coverage = (1 + 0.27 + 1 + 1 + 0) / 5 = **0.65**
* urgency: spinach expires in 1 day, so 1/(1+1) = 0.5, divided by 2 = **0.25**
* score = 100 × (0.7 × 0.65 + 0.3 × 0.25) = **53.2**

The API explains itself:

```
"You have 3 of 5 key ingredients."
"Uses spinach, which expires in 1 day."
"Only missing: canned tomatoes, spinach."
```

Explainable results are easier to trust, easier to debug and good to talk about in interviews.

---

## 6. The planner (`core/planner.py`), the heart of the project

### 6.1 The naive approach and why it fails

Naive: "for each slot, pick the best recipe". Problem: Monday's soup and Tuesday's soup both *claim* the same 200 g of
lentils, so the app says "you have everything" for both, which is false.

### 6.2 Our approach: simulate

1. Make a **copy** of the pantry (the real one is never touched while planning).
2. For each day, for each meal (breakfast, lunch, dinner):
   1. List the recipes allowed for that meal and diet.
   2. Score each one against the **simulated** pantry.
   3. Pick the best.
   4. **Cook it in the simulation**: remove its ingredients (first-expiring-first-out).
   5. Whatever the simulation could not provide goes on the **to-buy** list.
3. When all slots are filled, the to-buy list is the shopping list, and it is exact.

### 6.3 The score

```
50 × coverage + 20 × urgency + 15 × calorie fit + 10 × variety + 5 × shared shopping − 12 × times already used
```

* **calorie fit:** compares the recipe's calories per serving with this meal's share of your daily target
  (breakfast 25 %, lunch 35 %, dinner 40 %);
* **variety:** a bonus if the cuisine differs from the previous meal;
* **shared shopping:** a small bonus if the recipe reuses an ingredient we already plan to buy (less waste);
* **times already used:** the "do not eat the same thing every day" penalty. `max_repeats` caps it.

### 6.4 Walk-through (real output from the tests)

Pantry: 400 g red lentils, 3 onions, 8 garlic, 4 carrots, 2 lemons, 200 g spinach (expires tomorrow),
400 g chickpeas, 800 g canned tomatoes. Plan: lunch + dinner for 2 days, cooking for 3 people.

| Day | Meal | Recipe | Coverage | Missing |
|---|---|---|---|---|
| Oct 25 | lunch | Chickpea Spinach Curry | 100 % | nothing (uses the expiring spinach) |
| Oct 25 | dinner | Red Lentil Soup | 100 % | nothing |
| Oct 26 | lunch | Chickpea Spinach Curry | 60 % | chickpeas, garlic, spinach |
| Oct 26 | dinner | Red Lentil Soup | 60 % | garlic, onion |

Day 2 drops to 60 % **because day 1 already used the ingredients**. That is the simulation working. The shopping
list: `chickpeas 400 g, garlic 4 pcs, onion 1 pcs, spinach 100 g`.

### 6.5 Honest limits

* It is **greedy**: it picks the best option now, not the best combination for the week. Good enough, easy to explain,
  and deterministic (ties are broken by recipe id). A smarter version could use look-ahead.
* If the catalog cannot reach your calorie target, the plan says so instead of staying silent:
  `"The plan averages 1520 kcal per day, 24% below your 2000 kcal target. Add 'snack' to the meals list..."`
* Pantry food that will expire unused triggers a warning.

---

## 7. The shopping list (`core/grocery.py`)

Three small but important rules:

1. **Round up to something you can buy.** 37 g becomes 40 g, 231 g becomes 240 g, 1.2 pieces becomes 2 pieces.
2. **Group by aisle** (`produce`, `dairy & eggs`, ...), so it matches how you walk through a shop.
3. **Staples never appear.** Salt, oil and spices are assumed to be in your kitchen.

---

## 8. Nutrition (`core/nutrition.py`)

Each ingredient stores calories and macros **per 100 g**. For a recipe:

```
grams of ingredient  = quantity converted to grams
nutrition            = grams / 100 × value per 100 g
recipe per serving   = sum over ingredients / servings
```

Example, Masala Omelette (2 servings): 4 eggs = 200 g, and eggs have 143 kcal per 100 g, so eggs give 286 kcal.
Add butter and vegetables, divide by 2, and you get **203 kcal per serving** with 13.6 g protein, 6.1 g carbs and
13.8 g fat. Calories from each macro (4, 4 and 9 kcal per gram) give a split of 27 % protein, 12 % carbs, 61 % fat.

If an ingredient has no nutrition data (imported recipes), the recipe is marked `nutrition_complete: false`.
**Wrong numbers are worse than missing numbers.**

---

## 9. The cooking guide (`core/cooking_guide.py`)

Given a recipe, your pantry and the number of portions, it returns:

1. **Scaled ingredients.** Recipe for 3, you want 4: multiply by 4/3 (chickpeas 400 g become 533 g).
2. **Pantry status** for each: `in_pantry`, `partial`, `missing`, `staple`.
3. **Mise en place:** a prep list built from the notes ("Onion (1 pcs): finely chopped.").
4. **Timed steps** with a running clock (`starts_at_min`), a tip where it helps, and a `passive` flag for
   simmering or baking time when your hands are free.
5. **Substitutions** only for what you are missing: no spinach? use kale, chard or fenugreek leaves.

The step texts live in `app/seed/catalog.py`. Writing good steps (temperatures, times, "how to know it is done") is
what makes the guide actually useful, and it is content you can extend.

---

## 10. The third-party API (`integrations/themealdb.py`)

TheMealDB is a free public recipe API. We import recipes from it so the catalog can grow.

Real-world data is messy, so the importer has to cope:

| Messy input | What we do |
|---|---|
| `"1 1/2 cups"` | parsed as 1.5 cup |
| `"200g"` | parsed as 200 g |
| `"2"` | 2 pieces |
| `"to taste"` | no number: store as an **optional** ingredient |
| unknown ingredient name | create it, with `nutrition_known = false` |
| a paragraph of instructions | split into steps, and read "bake for 30 minutes" into a duration |
| importing the same meal twice | returns the existing recipe (idempotent) |

Two professional touches: the HTTP function is **injected**, so tests use a fake and never touch the network, and
a failure becomes a clean `502`, not a crash.

---

## 11. The database layer (`app/repositories/`)

Repositories contain **only SQL**. Three things to point out in an interview:

**Aggregation query** (pantry totals per ingredient):

```sql
SELECT i.name, SUM(p.quantity) AS total_quantity, COUNT(*) AS batches, MIN(p.expires_on) AS nearest_expiry
FROM pantry_items p JOIN ingredients i ON i.id = p.ingredient_id
WHERE p.user_id = ? AND p.quantity > 0
GROUP BY i.id ORDER BY i.category, i.name;
```

**Avoiding the N+1 problem.** Loading 19 recipes naively would run 1 + 19 + 19 queries. `load_recipes` runs exactly
**three**: recipes, all their ingredients, all their steps, then stitches them together in Python.

**Transactions.** "I cooked it" must deduct ingredients **and** mark the meal as cooked, or do neither:

```python
with conn:                              # commit if the block succeeds, roll back if it raises
    pantry_repo.apply_deductions(conn, result.deductions)
    plan_repo.mark_cooked(conn, meal_id)
```

---

## 12. Authentication and security

* `POST /auth/register`: stores a **PBKDF2-SHA256 hash** (200 000 rounds, random salt), never the password.
* `POST /auth/login`: checks the hash, returns a **JWT** that expires after 24 h.
* Every protected route uses the `current_user` dependency: it reads the token, validates it and loads the user.
* **Per-user isolation:** every query includes `user_id`. If you ask for another user's plan you get **404**, so the
  app does not even reveal that it exists. A test covers this.
* The same error message for "unknown email" and "wrong password" stops people discovering which emails exist.
* The app **refuses to start** without a proper `JWT_SECRET`. There is no default secret, so nobody can deploy by accident with a guessable one.

---

## 13. The web layer (`app/routers/`)

Routers are deliberately thin. Each one does the same four things:

1. validate input (Pydantic schemas: `days` must be 1 to 14, passwords at least 8 characters);
2. call a service or repository;
3. turn domain errors into HTTP status codes (`NotFound` becomes 404, `Conflict` becomes 409, `UnitError` becomes 422);
4. return JSON.

Detail that trips people up: in FastAPI the fixed path `/recipes/suggestions` must be declared **before**
`/recipes/{recipe_id}`, otherwise "suggestions" is read as an id and fails.

`create_app()` is a **factory function**, so tests can build an app with their own settings instead of importing a
global one.

---

## 14. Tests: what each file proves

| File | Proves |
|---|---|
| `test_units.py` | conversions are right, impossible ones raise, formatting reads well |
| `test_stock.py` | earliest-expiry first, expired food ignored, shortfall reported, simulation copies do not leak |
| `test_matcher.py` | coverage maths, staples ignored, expiring food raises the score, filters work |
| `test_planner.py` | weekly shape, deterministic, **pantry never spent twice**, shopping list = replay of the plan, vegan filter, warnings, bad input rejected |
| `test_grocery_nutrition_guide.py` | rounding, aisle sorting, nutrition maths, guide statuses, scaling, timeline |
| `test_repositories_services.py` | seed data, private recipes, SQL aggregation, **cooking is all-or-nothing**, users cannot touch each other's plans |
| `test_security_and_import.py` | hashing, JWT expiry and tampering, API import with a fake network |
| `test_api.py` | the same journey through real HTTP: register, pantry, suggest, plan, guide, cook |

Run them:

```bash
pytest -v
ruff check .
```

A habit worth copying: when a test failed during development, the question was **"is the test wrong or is the code
wrong?"**, never "make it green". Twice the test expectation was wrong (we had mis-calculated how much of an ingredient
one serving uses), and we fixed the test, not the code.

---

## 15. Docker and CI

* **Dockerfile:** small Python image, installs requirements first (so Docker caches that layer), runs as a non-root user, has a health check.
* **docker-compose.yml:** one service plus a named volume so the SQLite file survives restarts. It refuses to start
  without `JWT_SECRET`.
* **GitHub Actions (`ci.yml`):** on every push and pull request it installs dependencies, runs `ruff` and `pytest` on
  Python 3.11 and 3.12, and then builds the Docker image. The green badge in the README is real proof for recruiters.

---

## 16. Publish to GitHub

```bash
git add .
git commit -m "feat: pantry-aware meal planner with cooking guide"
git branch -M main
git remote add origin https://github.com/SaiKiran0078/mealmate-pro.git
git push -u origin main
```

Tips that make the repository look professional:

* **Commit in small steps** with clear messages: `feat: add unit conversion`, `test: cover first-expiring-first-out`,
  `docs: add architecture notes`, `ci: run tests on 3.11 and 3.12`. A history of 15 small commits beats one giant commit.
* Update the repository URL if you publish under a different GitHub repository. The LICENSE copyright holder is set to the project author.
* Add a repo description and topics: `fastapi`, `python`, `meal-planner`, `sqlite`, `jwt`, `docker`.
* After the first CI run, check the badge is green. Take a screenshot of `/docs` (Swagger UI) for the README.
* **Never commit `.env`** (it is in `.gitignore`).

---

## 17. Talking about it in interviews

**30-second pitch.** "MealMate Pro is a pantry-aware meal planner. Instead of starting from recipes, it starts from
what you already have, including expiry dates. It scores recipes by pantry coverage and urgency, generates daily or
weekly plans by simulating the pantry so nothing is double-counted, and produces an exact shopping list. It also
gives step-by-step cooking guidance and can import recipes from TheMealDB. It is FastAPI and SQLite with JWT auth,
tests, Docker and CI."

**Resume bullets (adapt, and only keep what you can explain):**

* Designed a pantry-aware meal planning engine in Python that simulates inventory consumption (first-expiring-first-out) to generate exact shopping lists.
* Modelled recipes, ingredients and pantry batches in SQLite with a many-to-many junction table; wrote aggregation queries and removed N+1 loading.
* Built a REST API with FastAPI, JWT authentication and per-user data isolation; integrated the TheMealDB API with a resilient, testable client.
* Wrote a pytest suite (unit, integration and API tests) and set up GitHub Actions CI and Docker.

**Questions you should be ready for:**

| Question | Short answer |
|---|---|
| Why a base unit? | Convert once at the boundary, so core logic uses plain numbers; fewer unit bugs. |
| Why batches instead of one quantity per ingredient? | Different expiry dates; needed for first-expiring-first-out. |
| Why simulate the pantry in the planner? | Otherwise two meals can claim the same ingredient and the shopping list is wrong. |
| Is the planner optimal? | No. It is greedy, which is easy to explain and deterministic. I would explore look-ahead or an optimisation solver next. |
| How do you prevent users seeing each other's data? | Every query filters on `user_id`; other users' resources return 404; tests cover it. |
| What about SQLite in production? | Fine for a small deployment. The repository layer isolates SQL, so moving to PostgreSQL means changing one layer. |
| How is the external API tested? | The fetch function is injected, so tests use a fake. No network in CI. |
| What would you improve? | Migrations, a front end, better planning, rate limiting, per-user time zones. |

---

## 18. Common problems

| Problem | Fix |
|---|---|
| `RuntimeError: JWT_SECRET must be set...` | Put a random 16+ character `JWT_SECRET` in `.env` and start with `--env-file .env`. |
| `ModuleNotFoundError: app` | Run commands from the project root (the folder that contains `app/`). |
| `401 Invalid or missing token` in Swagger | Click **Authorize** and paste only the token (without the word "Bearer"). |
| `422 ... has no known weight per piece` | You gave pieces for something we only know in g or ml. Use `g`, `ml`, `cup` and so on. |
| Port 8000 already in use | `uvicorn ... --port 8001` |
| Tests pass locally but the Docker build fails | `.dockerignore` excludes `tests/`; the image contains only the app. That is intentional. |

---

## 19. Ideas to take it further

1. **Front end:** a React page with a pantry list, a weekly calendar and a "cook mode" that shows one step at a time with a timer.
2. **Expiry defaults:** if the user gives no date, suggest one from a shelf-life table (milk 7 days, spinach 4 days).
3. **Look-ahead planning:** try the best 3 recipes per slot and keep the best week (beam search).
4. **Leftovers:** a recipe for 4 cooked for 2 produces leftovers that can fill tomorrow's lunch.
5. **Price awareness:** add prices per ingredient and show the cost of the plan.
6. **Reminders:** a background job that emails "spinach expires tomorrow, here are 3 recipes".
7. **Migrations:** introduce Alembic and PostgreSQL.
