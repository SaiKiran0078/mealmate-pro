# Audit: why the four problems happened, and what changed

Findings come from reading the whole repository and tracing each symptom from the browser to SQL.
See "Verification status" at the bottom for exactly what has and has not been executed.

## 1. Overview page shows wrong or inconsistent values

| Symptom | Root cause | Fix |
|---|---|---|
| "Recipe ideas" is always 4 (or 0) | The number was `suggestions.length` of a request with `limit=4`, and recipes using none of the pantry were included | `GET /dashboard` counts **recipes you can cook now** (all essential ingredients in stock) and **almost ready** over the whole catalog |
| Pantry count changes after visiting the Pantry page | The overview counted ingredients (`/pantry` summary); the Pantry page overwrote the same badge with the number of *batches* | One definition everywhere: distinct ingredients with in-date stock; batches are shown separately |
| "Expiring soon" lists spoiled food as "Until ..." | `expiring()` used `expires_on <= today+3`, which includes dates already past | Expiring (0-3 days left) and **expired** are separate lists with separate labels |
| Quantities have no unit or are stale | The UI read `item.unit` (the API sends `base_unit`) and showed the originally *typed* amount (`entered_amount`), so cooking never changed the display | The API returns `display` = remaining amount; the typed amount is shown only as "Added as ..." |
| Used-up items stay in the pantry list | `list_items` had no `quantity > 0` filter, while the totals did | Depleted batches are no longer listed |
| Planned calories too high / doubled | `/nutrition/daily` multiplied by the plan's `servings` (portions cooked) and summed **every** saved plan covering the date | Per person (one serving per planned meal); newest plan wins per meal slot |

## 2. Saved meal plans "do not persist"

The backend write path was sound (transaction, commit, user scoping). What users saw was a combination of:

* **The UI could not display a plan.** `renderPlanResult` looked for `days_detail`, `plan`, `meals_by_day` or `schedule`; the API returns `days`. Both a freshly generated and a re-opened plan fell through to a raw-JSON dump, so saved plans looked broken. Plan rows were also labelled with fields that do not exist (`title`, `name`).
* **Success was reported without confirmation.** The toast said "ready" regardless. Now `saved: true` is returned only after the plan is read back from the database; otherwise the page says "NOT SAVED". Empty plans are no longer saved.
* **The database location depended on the working directory.** `MEALMATE_DB=mealmate.db` was relative to wherever uvicorn was started, so starting from another folder silently created a second, empty database. Relative paths now resolve against the project folder, `.env` is read from the project folder, and the absolute path is logged at startup.
* Missing features users expect from "saved": delete, swap a meal, mark cooked from the UI. Added.

## 3. Pantry ingredients do not produce recipe recommendations

* **Name matching was too naive.** `find_or_create` only stripped a trailing "s": `tomatoes` became `tomatoe`, `chicken` never matched `chicken breast`, `lentils` never matched `red lentils`. Each miss silently created a brand-new ingredient with no nutrition data that no recipe uses, so coverage stayed at 0%. Fixed with `app/core/names.py` (plurals, spelling variants, a small explicit alias table; deliberately *not* fuzzy: "coconut milk" is not "milk").
* The add-ingredient response now says when a name was matched (`matched_as`) or is new (`created_new`, with "did you mean" hints), and the form suggests catalog names.
* **Existing databases are repaired at startup** (`repair_duplicates`): look-alike ingredients created by the old code are merged into the catalog entry, converting units through grams where needed. Idempotent.
* Recommendations ranked recipes with 0% coverage; picks now require some pantry overlap, and each result has `status` (ready / almost / missing) and substitution suggestions.

## 4. Recipe search returns nothing relevant

* `GET /recipes?q=` was `q in title`. Ingredients ("paneer", "eggs"), cuisines, nutrition goals ("high protein breakfast") and multi-word queries could never match.
* New `app/core/search.py` and `GET /recipes/search`: filters (meal type, diet, time, calories, protein) are parsed out of the text; remaining words must **all** match title / ingredients / cuisine; prefix and plural tolerant; relevance-ranked; sort by relevance, time, calories, protein or pantry match; pagination; each hit includes pantry coverage and missing items. No match gives an explanation and clearly labelled partial matches, never unrelated recipes.
* TheMealDB is searched only on request (`include_external=true` / button), listed separately and labelled; failures are shown as errors, never replaced by invented results.

## Verification status (honest)

Verification run for this revision:

* Python: `python -m pytest` — **137 passed**.
* JavaScript: `node --test tests/js/render.test.js` — **7 passed**.
* Syntax: `node --check app/static/app.js`, `node --check app/static/render.js`, and `python -m compileall -q app tests` passed.
* Regression coverage includes pantry plural matching, ready and partial recipe suggestions, saved-plan persistence, user-scoped favourites/ratings, and adding a new built-in recipe to an existing database.
* **Not verified here:** a live browser session against a user's actual database, real external TheMealDB availability, USDA credentials, Docker build, and Ruff (the Ruff module was not available in this environment). Run `ruff check .` in the project virtual environment before release.

## Master-prompt scope: implemented vs not

The master prompt describes a React + TypeScript + PostgreSQL + Alembic rewrite with an LLM recipe generator. You also asked to preserve the working architecture and avoid rewrites, so this change stays on FastAPI + SQLite + the built-in HTML/JS UI.

Implemented or improved: pantry (add, edit remaining amount, delete, expiry, expired/expiring, name matching, export via API), pantry-based recommendations below pantry cards with ready / almost ready / missing and substitutions, personal recipe favourites and 1–5 ratings, working recipe search with filters, sorting and pagination, nutrition per serving, daily/weekly plans that persist (list, open, delete, swap, mark cooked with confirmed pantry deduction), shopping list from a plan against the pantry, fitness targets (Mifflin-St Jeor), food diary, workouts, overview dashboard.

**Not implemented** (needs new schema/services and, for some, external credentials): React/TypeScript frontend, PostgreSQL/Alembic, AI recipe generation and any LLM provider layer, recipe collections/notes, pantry import/export UI, low-stock alerts, shopping-list persistence and purchase tracking, plan duplication / moving meals / per-meal regeneration, body-weight and protein-goal timelines, budget/price data, password recovery, account deletion/data export, rate limiting, full micronutrient coverage (USDA import exists but needs `USDA_FDC_API_KEY`).
