// Run with:  node --test tests/js
const test = require("node:test");
const assert = require("node:assert");
const R = require("../../app/static/render.js");

const generated = {
  plan_id: 7, servings: 2,
  days: [{ date: "2026-10-28", nutrition: { totals: { kcal: 1850, protein_g: 80 }, percent_of_target: 92 },
    meals: [{ meal_id: 1, meal_type: "breakfast", recipe_id: 3, title: "Masala <Omelette>", total_min: 12, cooked: false,
              missing: ["egg"], nutrition_per_serving: { kcal: 320, protein_g: 18 } },
            { meal_id: 2, meal_type: "lunch", recipe_id: 4, title: "Soup", total_min: 30, cooked: true, nutrition_per_serving: { kcal: 400, protein_g: 20 } }] }],
  average_daily_nutrition: { totals: { kcal: 1850 } }, warnings: ["Not enough lunches."],
  grocery_list: [{ name: "egg", display: "4 pcs" }],
};

test("a plan response (days array) renders as a day-by-day schedule, not a JSON dump", () => {
  const html = R.planHtml(generated);
  assert.match(html, /SAVED · PLAN #7/);
  assert.match(html, /Masala &lt;Omelette&gt;/);          // titles are escaped
  assert.match(html, /1850 kcal/);
  assert.match(html, /data-cook-meal="1"/);               // uncooked meal can be cooked
  assert.doesNotMatch(html, /data-cook-meal="2"/);        // cooked one cannot
  assert.match(html, /COOKED/);
  assert.match(html, /Need: egg/);
  assert.match(html, /Not enough lunches/);
  assert.match(html, /4 pcs/);
  assert.doesNotMatch(html, /could not be displayed/);
});

test("an unsaved plan is labelled NOT SAVED and has no delete or cook buttons", () => {
  const html = R.planHtml({ ...generated, plan_id: null });
  assert.match(html, /NOT SAVED/);
  assert.doesNotMatch(html, /data-plan-delete|data-cook-meal/);
});

test("overview stats use the server numbers and distinguish expired from expiring", () => {
  const s = R.overviewStats({
    pantry: { ingredients: 7, batches: 9, expiring_soon: [{}, {}], expired: [{}] },
    recipes: { ready_to_cook: 5, almost_ready: 3 }, plans: { count: 2 },
  });
  assert.deepStrictEqual([s.ingredients, s.expiring, s.ready, s.plans], [7, 2, 5, 2]);
  assert.match(s.ingredientsNote, /9 batches/);
  assert.match(s.expiringNote, /1 already past date/);
  assert.match(s.readyNote, /\+3 almost ready/);
});

test("pantry card shows the remaining amount and flags expired stock", () => {
  const html = R.pantryCardHtml({ id: 1, name: "rice", display: "750 g", entered_amount: 1, entered_unit: "kg", status: "expired", expires_on: "2026-10-01" });
  assert.match(html, /750 g/);
  assert.match(html, /Added as 1 kg/);
  assert.match(html, /Expired/);
});

test("recipe card shows ready / partial pantry match and missing ingredients", () => {
  const recipe = { id: 1, title: "Paneer Bhurji", meal_types: ["dinner"], total_min: 20, difficulty: "easy", servings: 2, nutrition_per_serving: { kcal: 300, protein_g: 20 } };
  assert.match(R.recipeCardHtml({ recipe, status: "ready", can_cook_now: true, coverage_pct: 100, missing: [] }), /Ready to cook/);
  const html = R.recipeCardHtml({ recipe, status: "almost", can_cook_now: false, coverage_pct: 75, missing: [{ name: "paneer" }] });
  assert.match(html, /75% of your pantry/);
  assert.match(html, /Missing: paneer/);
});

test("empty search shows explanation, partial matches and an external-search button, never unrelated cards", () => {
  const html = R.searchResultsHtml({ query: "chicken biryani", results: [], related: [], suggestions: ["Try 'chicken'."], interpreted: { notes: [] } });
  assert.match(html, /No recipes matched/);
  assert.match(html, /data-search-external/);
  assert.doesNotMatch(html, /recipe-card/);
});

test("external results are labelled with their source and API errors are shown, not hidden", () => {
  const html = R.searchResultsHtml({ query: "x", results: [], related: [], suggestions: [], external: [{ title: "Biryani", category: "Chicken", area: "Indian" }], external_error: "boom" });
  assert.match(html, /from TheMealDB/);
  assert.match(html, /TheMealDB is unavailable/);
});
