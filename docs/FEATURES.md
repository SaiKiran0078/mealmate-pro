# MealMate Pro — Feature and data-quality notes

## Included workflows

- Account registration and login with per-user data isolation.
- Pantry batch inventory, expiry-aware recipe matching, meal plans and shopping lists.
- Live external recipe discovery and import through TheMealDB.
- Responsive browser dashboard for pantry, meal plans, profile targets, food diary, workout logs and recipe discovery.
- Fitness profile with estimated energy and macro targets for fat loss, muscle gain, maintenance or general health.
- Actual food diary, separate from planned meals, with daily planned-vs-consumed comparison.
- Workout history and general pre/post-workout recipe suggestions.
- Optional source-attributed micronutrient lookup/import through USDA FoodData Central.

## Data quality

- Calories/macros are only complete when ingredient data is known; external recipes with unknown ingredients remain flagged as incomplete.
- USDA micronutrient import requires the optional `USDA_FDC_API_KEY` environment variable. Source name and FoodData Central record ID are retained.
- Micronutrient coverage is intentionally partial: supported facts are returned, absent facts are not filled with guessed zeros.
- Fitness target calculations are estimates for planning and should not be used to diagnose or treat a medical condition.
- Workout fueling suggestions are general education and do not replace individualized sports-nutrition guidance.

## Smoke test

1. Start the app and open `/`.
2. Create an account and log in.
3. Save a fitness profile and confirm targets appear.
4. Add pantry ingredients, request pantry suggestions and generate a one-day plan.
5. Log a food diary entry and compare it with planned nutrition.
6. Save a workout and request pre/post-workout ideas.
7. Search TheMealDB. To test USDA micronutrients, configure `USDA_FDC_API_KEY`, search for a food and import its FDC record to a matching ingredient.


## Pantry recommendations and personal recipe collection

- The My Pantry page loads partial and ready recipe matches below the ingredient cards. Matches include coverage, missing ingredients, and expiry-aware ranking.
- New built-in recipes are seeded idempotently at startup, so existing databases receive catalog additions without replacing the user's pantry or account data.
- Users can favourite recipes and save a 1–5 star personal rating. Feedback is scoped to the signed-in user.
- The Find Recipes page can search the local catalog and optionally query TheMealDB; external results are labelled and can be imported into the local catalog.
