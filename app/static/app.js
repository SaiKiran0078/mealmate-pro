(() => {
  "use strict";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = { token: localStorage.getItem("mealmate_token") || "", user: null, pantry: [], recipes: [], suggestions: [], plans: [], authMode: "login" };
  const { esc, foodEmoji, fmtDate } = window.MealMateRender;
  const RM = window.MealMateRender;
  // Keep nutrition decimals visible (e.g. 13.4 g) without noisy trailing zeros.
  const nutritionNumber = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return "0";
    return number.toLocaleString(undefined, { maximumFractionDigits: 1 });
  };
  const NUTRIENT_META = [
    ["Calories", "kcal", "kcal", "🔥"],
    ["Protein", "protein_g", "g", "💪"],
    ["Carbohydrates", "carbs_g", "g", "🌾"],
    ["Fat", "fat_g", "g", "💧"],
  ];
  const nutritionProgress = (label, amount, target, unit, sourceLabel, icon) => {
    const actual = Math.max(0, Number(amount) || 0);
    const goal = Number(target);
    if (!Number.isFinite(goal) || goal <= 0) return "";
    const percent = Math.round(actual / goal * 100);
    const remaining = Math.max(0, goal - actual);
    const status = actual >= goal
      ? `${nutritionNumber(actual - goal)} ${unit} over plan`
      : `${nutritionNumber(remaining)} ${unit} remaining`;
    return `<article class="nutrition-progress"><div class="nutrition-progress-heading"><span class="nutrition-label"><span class="nutrition-icon" aria-hidden="true">${icon}</span>${esc(label)}</span><strong>${percent}%</strong></div><div class="nutrition-progress-track" role="progressbar" aria-label="${esc(sourceLabel)} ${esc(label)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.min(100, percent)}"><span style="width:${Math.min(100, Math.max(0, percent))}%"></span></div><small>${nutritionNumber(actual)} / ${nutritionNumber(goal)} ${esc(unit)} · ${esc(status)}</small></article>`;
  };
  const eatenOnlyCard = (label, amount, unit, icon) => `<article class="nutrition-progress eaten-only-card"><div class="nutrition-progress-heading"><span class="nutrition-label"><span class="nutrition-icon" aria-hidden="true">${icon}</span>${esc(label)}</span></div><strong class="eaten-only-value">${nutritionNumber(amount)} <small>${esc(unit)}</small></strong><small>Logged today</small></article>`;
  const remainingNutritionHtml = (consumed = {}, targets = null, planned = null) => {
    const hasPlanned = planned && Number(planned.entries) > 0;
    if (!hasPlanned) {
      return `<section class="nutrition-progress-section"><h4 class="nutrition-progress-title">Eaten nutrition <span class="nutrition-context">From logged foods · no meal plan</span></h4><div class="nutrition-progress-grid eaten-only-grid">${NUTRIENT_META.map(([label,key,unit,icon]) => eatenOnlyCard(label, consumed[key], unit, icon)).join("")}</div></section>`;
    }
    const rows = NUTRIENT_META.map(([label,key,unit,icon]) =>
      nutritionProgress(label, consumed[key], planned[key], unit, "Eaten against planned nutrition", icon)
    ).join("");
    return `<section class="nutrition-progress-section"><h4 class="nutrition-progress-title">Eaten vs planned nutrition <span class="nutrition-context">Per-person planned totals</span></h4><div class="nutrition-progress-grid">${rows}</div></section>`;
  };
  const showToast = (message, type = "success") => {
    const el = document.createElement("div"); el.className = `toast ${type === "error" ? "error" : ""}`; el.textContent = message; $("#toast-region").append(el); setTimeout(() => el.remove(), 4200);
  };
  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
    let response;
    try { response = await fetch(path, {...options, headers, cache: options.cache || "no-store"}); }
    catch { throw new Error("Could not connect to MealMate. Check that the FastAPI server is running."); }
    if (response.status === 204) return { ok: true };
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = data && typeof data === "object" ? data.detail : data;
      const message = Array.isArray(detail) ? detail.map(e => { const raw = e.msg || "Please check this field."; return String(raw).replace(/Input should be a valid integer/gi, "Please enter a whole number").replace(/Field required/gi, "Please fill in this field").replace(/less than or equal to/gi, "must be no more than").replace(/greater than or equal to/gi, "must be at least"); }).join(". ") : (detail || `Request failed (${response.status})`);
      if (response.status === 401 && state.token) logout(false);
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  }
  const withBusy = async (button, action, busyText = "Please wait…") => {
    const old = button?.innerHTML; if (button) { button.disabled = true; button.innerHTML = busyText; }
    try { return await action(); } catch (e) { showToast(e.message || "Something went wrong.", "error"); return null; }
    finally { if (button) { button.disabled = false; button.innerHTML = old; } }
  };
  const authScreen = (mode = "login") => {
    state.authMode = mode;
    $("#auth-screen").classList.remove("hidden"); $("#app-shell").classList.add("hidden");
    $$(".auth-tab").forEach(b => b.classList.toggle("active", b.dataset.authTab === mode));
    $("#auth-title").textContent = mode === "login" ? "Good to see you again." : "Let's get you started.";
    $("#auth-subtitle").textContent = mode === "login" ? "Sign in to pick up where your appetite left off." : "Create your account and make your kitchen work smarter.";
    $("#auth-submit").innerHTML = mode === "login" ? 'Sign in <span>→</span>' : 'Create account <span>→</span>';
    $("#auth-password").autocomplete = mode === "login" ? "current-password" : "new-password";
    $("#auth-switch").innerHTML = mode === "login" ? 'New to MealMate? <button type="button" data-auth-tab="register">Create an account</button>' : 'Already have an account? <button type="button" data-auth-tab="login">Sign in</button>';
  };
  async function logout(notify = true) {
    state.token = ""; state.user = null; localStorage.removeItem("mealmate_token"); localStorage.removeItem("mealmate_email");
    $("#app-shell").classList.add("hidden"); $("#auth-screen").classList.remove("hidden"); authScreen("login");
    if (notify) showToast("You have signed out.");
  }
  function enterApp(user) {
    state.user = user;
    if (user?.email) localStorage.setItem("mealmate_email", user.email);
    $("#auth-screen").classList.add("hidden"); $("#app-shell").classList.remove("hidden");
    const email = user?.email || "My account", initial = email.charAt(0).toUpperCase() || "M";
    $("#profile-email").textContent = email; $("#avatar-initial").textContent = initial; $("#top-avatar").textContent = initial;
    $("#welcome-title").textContent = `Let's make something good${email.split("@")[0] ? `, ${email.split("@")[0]}` : ""}.`;
    $("#today-label").textContent = new Date().toLocaleDateString(undefined,{weekday:"short",day:"numeric",month:"short"});
    const lastPage = localStorage.getItem("mealmate_last_page") || "dashboard";
    navigate(lastPage, { save: false });
  }
  async function restoreSession() {
    if (!state.token) return authScreen();
    try {
      const user = await api("/me");
      enterApp(user);
    } catch (error) {
      // A 401 means the stored token is no longer valid. Network/5xx failures
      // must not erase a valid token or the user's last visited section.
      if (error.status === 401) {
        state.token = "";
        localStorage.removeItem("mealmate_token");
        authScreen("login");
        showToast("Your session expired. Please sign in again.", "error");
        return;
      }
      const cachedEmail = localStorage.getItem("mealmate_email") || "My account";
      enterApp({ email: cachedEmail });
      showToast("Couldn't verify your session right now. Your saved session was kept; try again when the connection is back.", "error");
    }
  }
  function navigate(page, options = {}) {
    const valid = ["dashboard","pantry","recipes","plans","fitness","preferences"].includes(page) ? page : "dashboard";
    if (options.save !== false) localStorage.setItem("mealmate_last_page", valid);
    $$(".page").forEach(p => p.classList.toggle("active", p.id === `page-${valid}`));
    $$(".nav-item[data-page]").forEach(b => b.classList.toggle("active", b.dataset.page === valid));
    const titles = {dashboard:"Overview",pantry:"My pantry",recipes:"Find recipes",plans:"Meal planner",fitness:"Fitness & nutrition",preferences:"Preferences"};
    $("#current-section").textContent = titles[valid]; $("#sidebar").classList.remove("open");
    if (valid === "dashboard") { loadDashboard(); loadFavorites(); }
    if (valid === "pantry") loadPantry();
    if (valid === "recipes") loadRecipes();
    if (valid === "plans") { loadPlans(); loadPlanPantryPicks(); loadFavorites(); }
    if (valid === "fitness") loadFitness();
    if (valid === "preferences") loadPreferences();
    window.scrollTo({top:0,behavior:"smooth"});
  }
  const empty = RM.empty;
  async function loadDashboard() {
    try {
      const [d, dailyNutrition] = await Promise.all([api("/dashboard"), api("/nutrition/daily")]);
      const st = RM.overviewStats(d);
      $("#stat-ingredients").textContent = st.ingredients; $("#stat-ingredients-note").textContent = st.ingredientsNote;
      $("#stat-expiring").textContent = st.expiring; $("#stat-expiring-note").textContent = st.expiringNote;
      $("#stat-recipes").textContent = st.ready; $("#stat-recipes-note").textContent = st.readyNote;
      $("#stat-plans").textContent = st.plans;
      $("#pantry-nav-count").textContent = st.ingredients;
      $("#expiring-list").innerHTML = RM.useSoonHtml(d.pantry);
      const picks = d.recipes.picks;
      $("#dashboard-recipes").innerHTML = picks.length ? picks.map(m => {
        const r = m.recipe, b = RM.badgeFor(m);
        return `<div class="mini-recipe"><span class="mini-food-icon">${foodEmoji(r.title)}</span><div class="mini-recipe-info"><strong>${esc(r.title)}</strong><small>${esc(r.total_min)} min · ${esc(b.text)}</small></div><button data-recipe-open="${esc(r.id)}" aria-label="Open ${esc(r.title)}">↗</button></div>`;
      }).join("") : empty(d.pantry.ingredients ? "No recipe uses your current ingredients yet. Add a few more." : "Add pantry ingredients to get recipe ideas.");
      const t = d.plans.today, n = d.nutrition_today;
      $("#today-plan").innerHTML = t.length
        ? t.map(m => `<div class="compact-row"><span class="ingredient-symbol">${foodEmoji(m.title)}</span><div class="compact-info"><strong>${esc(m.title)}</strong><small>${esc(m.meal_type)}${m.cooked ? " · cooked" : ""}</small></div></div>`).join("")
        : empty("Nothing planned for today. Generate a plan to fill it.");
      const consumed = dailyNutrition.consumed || n.consumed || {};
      const planned = dailyNutrition.planned || n.planned || {};
      const hasPlannedMeals = Number(planned.entries) > 0 || t.length > 0;
      const targets = dailyNutrition.targets || (n.target_kcal ? {daily_kcal:n.target_kcal} : null);
      // Keep the Overview's planned/eaten summaries in lockstep with Fitness & Nutrition.
      // Planned meals are a forecast; personal daily targets are a separate goal and must not
      // be overwritten by planned totals.
      const summaryCard = (title, row, emptyLabel = "") => `<div class="fitness-summary-card"><strong>${title}</strong>${emptyLabel
        ? `<span>${emptyLabel}</span><span>Add meals to your plan to see planned totals.</span>`
        : `<span>${nutritionNumber(row.kcal)} kcal</span><span>${nutritionNumber(row.protein_g)} g protein · ${nutritionNumber(row.carbs_g)} g carbs · ${nutritionNumber(row.fat_g)} g fat</span>`}</div>`;
      const plannedCard = hasPlannedMeals
        ? summaryCard("Planned (per person)", planned)
        : summaryCard("Planned (per person)", planned, "No meals planned");
      const eatenCard = summaryCard("Eaten so far", consumed);
      $("#today-nutrition").innerHTML = `${plannedCard}${eatenCard}${remainingNutritionHtml(consumed, targets, planned)}`;
    } catch (e) { showToast(e.message, "error"); }
  }
  async function loadPantry() {
    $("#pantry-items").innerHTML = '<div class="loading-line"></div>';
    try {
      const [batches, names] = await Promise.all([api("/pantry/batches"), api("/pantry/ingredients/search?q=")]);
      state.pantry = batches;
      $("#ingredient-options").innerHTML = names.map(i => `<option value="${esc(i.name)}">`).join("");
      const usable = new Set(batches.filter(b => b.status !== "expired").map(b => b.name));
      $("#pantry-nav-count").textContent = usable.size;
      $("#pantry-count-label").textContent = `${usable.size} ingredient${usable.size === 1 ? "" : "s"} in stock · ${batches.length} batch${batches.length === 1 ? "" : "es"}`;
      renderPantry();
      await loadPantryRecommendations();
    } catch (e) { $("#pantry-items").innerHTML = empty(e.message); }
  }
  async function loadPantryRecommendations() {
    const target = $("#pantry-recipe-results");
    if (!target) return;
    target.innerHTML = '<div class="loading-line"></div>';
    try {
      const rows = await api("/recipes/suggestions?min_coverage=0.15&limit=12");
      target.innerHTML = rows.length ? rows.map(RM.recipeCardHtml).join("") : empty("No recipes match your current pantry yet. Add more ingredients or search recipes online.");
      await loadFavorites();
    } catch (e) { target.innerHTML = empty(e.message); }
  }
  async function loadPlanPantryPicks() {
    const target = $("#plan-pantry-results"); if (!target) return;
    target.innerHTML = '<div class="loading-line"></div>';
    try {
      const rows = await api("/recipes/suggestions?min_coverage=0.15&limit=8");
      target.innerHTML = rows.length ? rows.map(RM.recipeCardHtml).join("") : empty("Add a few pantry ingredients to unlock personalised meal ideas. You can also search online in Find recipes.");
    } catch (e) { target.innerHTML = empty(e.message); }
  }
  async function loadGoalRecipes() {
    const target = $("#goal-recipe-results"); if (!target) return;
    target.innerHTML = '<div class="loading-line"></div>';
    try {
      const profile = await api("/fitness/profile");
      if (!profile.profile || !profile.targets) { target.innerHTML = empty("Save your fitness profile first, then refresh these recommendations."); return; }
      const goal = profile.profile.goal;
      const sort = goal === "muscle_gain" ? "protein" : goal === "fat_loss" ? "calories" : "pantry";
      const data = await api(`/recipes/search?sort=${sort}&limit=12`);
      const recipes = data.results || [];
      target.innerHTML = recipes.length ? recipes.map(row => { const r = row.recipe || row; const coverage = row.coverage_pct ?? 0; const n = r.nutrition_per_serving || {}; return `<div class="compact-row"><span class="ingredient-symbol">${foodEmoji(r.title)}</span><div class="compact-info"><strong>${esc(r.title || "Recipe idea")}</strong><small>${r.nutrition_complete ? `${Math.round(n.kcal || 0)} kcal · ${Math.round(n.protein_g || 0)} g protein` : "Nutrition data is incomplete for this dish"} per serving · ${Math.round(coverage)}% pantry match</small></div><button class="text-button" data-recipe-open="${esc(r.id)}">View recipe →</button></div>`; }).join("") : empty("No matching recipes found yet. Try another goal or search for a dish in Find recipes.");
    } catch (e) { target.innerHTML = empty(e.message); }
  }
  function renderPantry() {
    const q = ($("#pantry-search").value || "").trim().toLowerCase();
    const filtered = state.pantry.filter(item => (item.name || "").toLowerCase().includes(q));
    $("#pantry-items").innerHTML = filtered.length ? filtered.map(RM.pantryCardHtml).join("") : `<div class="empty-state"><span>🥬</span><h3>${q ? "No matching ingredients" : "Your pantry is ready to fill"}</h3><p>${q ? "Try a different search." : "Add your first ingredient to start getting recipe ideas."}</p><button class="btn btn-primary" id="empty-add-pantry">＋ Add ingredient</button></div>`;
  }
  async function loadRecipes(extra = {}) {
    $("#recipe-grid").innerHTML = '<div class="loading-line"></div>';
    const q = $("#recipe-search").value.trim(), meal = $("#recipe-meal-filter").value, minutes = $("#recipe-time-filter").value;
    const params = new URLSearchParams({ sort: $("#recipe-sort").value, limit: "24" });
    if (q) params.set("q", q); if (meal) params.set("meal_type", meal); if (minutes) params.set("max_minutes", minutes);
    if ($("#cookable-filter").checked) params.set("min_coverage", "1");
    if (extra.external === true || $("#include-online-recipes")?.checked) params.set("include_external", "true");
    try {
      const res = await api(`/recipes/search?${params}`);
      state.recipes = res.results;
      $("#recipe-results-count").textContent = `${res.total} result${res.total === 1 ? "" : "s"}`;
      $("#recipe-results-title").textContent = q ? `Results for “${q}”` : "All recipes, best pantry match first";
      $("#recipe-grid").className = "";
      $("#recipe-grid").innerHTML = RM.searchResultsHtml(res);
      await loadFavorites();
    } catch (e) { $("#recipe-grid").innerHTML = empty(e.message); }
  }
  async function loadFavorites() {
    const target = $("#favourite-recipes-list");
    try {
      const [rows, feedback] = await Promise.all([api("/recipes/favorites"), api("/recipes/feedback")]);
      const listHtml = rows.length ? rows.map(r => `<div class="compact-row"><span class="ingredient-symbol">${foodEmoji(r.title)}</span><div class="compact-info"><strong>${esc(r.title)}</strong><small>${r.rating ? `Your rating: ${r.rating}/5` : "Not rated yet"} · ${esc(r.total_min ?? 0)} min</small></div><button class="text-button" data-recipe-open="${r.id}">View →</button><button class="text-button" data-unfavorite="${r.id}">Remove favourite</button></div>`).join("") : empty("Save a recipe with ♡ Favourite and it will appear here.");
      if (target) target.innerHTML = listHtml;
      const dashboardTarget = $("#dashboard-favourite-recipes-list");
      if (dashboardTarget) dashboardTarget.innerHTML = rows.length ? rows.slice(0, 4).map(r => `<div class="compact-row"><span class="ingredient-symbol">${foodEmoji(r.title)}</span><div class="compact-info"><strong>${esc(r.title)}</strong><small>${r.rating ? `Your rating: ${r.rating}/5` : "Not rated yet"} · ${esc(r.total_min ?? 0)} min</small></div><button class="text-button" data-recipe-open="${r.id}">View →</button><button class="text-button" data-unfavorite="${r.id}">Remove</button></div>`).join("") : empty("No favourites yet. Open Find recipes and tap ♡ Favourite to build your collection.");
      const count = $("#stat-favorites");
      if (count) count.textContent = String(rows.length);
      const feedbackById = new Map(feedback.map(item => [String(item.recipe_id), item]));
      $$(`[data-favorite-toggle]`).forEach(button => {
        const saved = feedbackById.get(button.dataset.favoriteToggle);
        const active = Boolean(saved?.favorite);
        button.dataset.active = String(active); button.setAttribute("aria-pressed", String(active));
        button.textContent = active ? "♥ Favourite" : "♡ Favourite";
      });
      $$(`[data-recipe-rating]`).forEach(select => {
        const saved = feedbackById.get(select.dataset.recipeRating);
        select.value = saved?.rating ? String(saved.rating) : "";
      });
    } catch (e) { if (target) target.innerHTML = empty(e.message); }
  }
  async function openRecipe(id, requestedServings = null) {
    if (id === "" || id == null) { showToast("This recipe does not have an available ID.", "error"); return; }
    $("#modal-content").innerHTML = '<div class="loading-line"></div><div class="loading-line"></div>';
    $("#recipe-modal").classList.remove("hidden");
    try {
      const recipe = await api(`/recipes/${encodeURIComponent(id)}`);
      const servings = Number(requestedServings || recipe.servings || 1);
      const guide = await api(`/recipes/${encodeURIComponent(id)}/guide?servings=${encodeURIComponent(servings)}`).catch(() => null);
      const STATUS = { in_pantry: "✓ in pantry", partial: "◐ not enough", missing: "✗ missing", staple: "staple" };
      const ingredients = (guide?.ingredients || recipe.ingredients || []).map(i => ({ ...i, status: i.status }));
      const steps = guide?.steps || recipe.steps || [];
      $("#modal-content").innerHTML = `<span class="eyebrow">YOUR NEXT KITCHEN ADVENTURE</span><h2 class="modal-title" id="modal-title">${esc(recipe.title || "Recipe")}</h2><p class="modal-description">${esc(recipe.description || "A delicious recipe to try at home.")}</p><div class="modal-meta"><span>◷ ${esc(recipe.total_min ?? ((recipe.prep_min||0)+(recipe.cook_min||0)))} min</span><span>♧ ${esc(recipe.difficulty || "Easy")}</span><label>Servings <input type="number" min="1" max="24" value="${esc(servings)}" id="modal-servings" style="width:76px;padding:6px;border:1px solid #dfe5dc;border-radius:8px"></label><button class="text-button" data-rescale-recipe="${esc(recipe.id)}">Update quantities</button></div>${guide ? `<p class="modal-description">${guide.can_cook_now ? "You have everything you need." : `Missing: ${esc((guide.missing || []).join(", "))}.`}</p>` : ""}${guide && !guide.can_cook_now && Object.keys(guide.substitutions || {}).length ? `<section class="modal-section"><h3>Swaps</h3>${Object.entries(guide.substitutions).map(([k, v]) => `<div class="ingredient-line"><strong>${esc(k)}</strong>: ${esc(v.join(" · "))}</div>`).join("")}</section>` : ""}${guide ? `<section class="modal-section"><h3>Estimated nutrition</h3><p class="modal-description">${guide.nutrition_complete ? `Per serving: ${Math.round(guide.nutrition_per_serving.kcal * 10) / 10} kcal · ${Math.round(guide.nutrition_per_serving.protein_g * 10) / 10} g protein · ${Math.round(guide.nutrition_per_serving.carbs_g * 10) / 10} g carbs · ${Math.round(guide.nutrition_per_serving.fat_g * 10) / 10} g fat.<br>Total for ${esc(guide.servings)} servings: ${Math.round(guide.nutrition_per_serving.kcal * guide.servings)} kcal · ${Math.round(guide.nutrition_per_serving.protein_g * guide.servings)} g protein · ${Math.round(guide.nutrition_per_serving.carbs_g * guide.servings)} g carbs · ${Math.round(guide.nutrition_per_serving.fat_g * guide.servings)} g fat.` : "Nutrition data is incomplete because some ingredients do not have known values. Figures shown may be partial."}</p></section>` : ""}${ingredients.length ? `<section class="modal-section"><h3>Ingredients for ${esc(guide?.servings || servings)} servings</h3><div class="ingredient-list">${ingredients.map(i => `<div class="ingredient-line">${esc(i.name)} · ${esc(i.quantity ?? "")}${i.note ? ` (${esc(i.note)})` : ""}${i.optional ? " (optional)" : ""}${i.status ? ` <small class="ing-status ${esc(i.status)}">${esc(STATUS[i.status] || "")}</small>` : ""}</div>`).join("")}</div></section>` : ""}${steps.length ? `<section class="modal-section"><h3>Let's get cooking</h3>${steps.map((s,i) => `<div class="guide-step"><span class="step-number">${i+1}</span><div><p>${esc(typeof s === "string" ? s : (s.instruction || s.text || ""))}</p>${s.duration_min != null ? `<small>◷ ${esc(s.duration_min)} min</small>` : ""}${s.tip ? `<small>✦ ${esc(s.tip)}</small>` : ""}</div></div>`).join("")}</section>` : `<p class="modal-description">Detailed cooking steps aren't available for this recipe yet.</p>`}`;
    } catch(e) { $("#modal-content").innerHTML = `<h2 class="modal-title" id="modal-title">Couldn't open this recipe</h2><p class="modal-description">${esc(e.message)}</p>`; }
  }
  async function loadPlans() {
    $("#saved-plans-list").innerHTML = '<div class="loading-line"></div>';
    try {
      state.plans = await api("/plans");
      $("#saved-plan-count").textContent = `${state.plans.length} PLAN${state.plans.length === 1 ? "" : "S"}`;
      $("#saved-plans-list").innerHTML = state.plans.length ? state.plans.slice(0, 12).map(RM.savedPlanRowHtml).join("") : empty("Your saved meal plans will appear here.");
    } catch (e) { $("#saved-plans-list").innerHTML = empty(e.message); }
  }
  function showPlan(html) { const root = $("#plan-result"); root.classList.remove("hidden"); root.innerHTML = html; root.scrollIntoView({ behavior: "smooth", block: "start" }); }
  async function generatePlan(button) {
    const meals = $$(".meal-checkboxes input[type=\'checkbox\']")
      .filter(input => input.checked)
      .map(input => input.value.trim().toLowerCase());
    if (!meals.length) { showToast("Choose at least one meal type.", "error"); return; }
    const body = { days: Number($("#plan-days").value), meals, save: $("#plan-save").checked };
    if ($("#plan-servings").value) body.servings = Number($("#plan-servings").value);
    if ($("#plan-diet").value) body.diet = $("#plan-diet").value;
    const timeChoice = $("#plan-cooking-time").value;
    if (timeChoice === "quick") body.max_minutes = 30;
    if (timeChoice === "easy") body.max_minutes = 45;
    body.pantry_first = $("#plan-pantry-mode").value === "pantry_first";
    const result = await withBusy(button, () => api("/plans/generate", { method: "POST", body: JSON.stringify(body) }), "Building your plan…");
    if (!result) return;
    if (result.saved) {
      // only claim success after the server read the plan back from the database
      await openPlan(result.plan_id, result);
      showToast(`Plan #${result.plan_id} saved.`);
    } else {
      showPlan(RM.planHtml(result));
      await loadFavorites();
      showToast(body.save ? "Plan generated, but nothing could be saved. See the notes below." : "Plan generated (not saved).", body.save ? "error" : "success");
    }
    loadPlans();
  }
  async function openPlan(id, generated) {
    try {
      const [plan, grocery] = await Promise.all([api(`/plans/${encodeURIComponent(id)}`), api(`/plans/${encodeURIComponent(id)}/grocery`)]);
      if (generated) { plan.warnings = generated.warnings; plan.average_daily_nutrition = generated.average_daily_nutrition; }
      showPlan(RM.planHtml(plan, { grocery }));
      await loadFavorites();
    } catch (e) { showToast(e.message, "error"); }
  }
  async function swapMeal(btn) {
    const { swapMeal: mealId, planId, mealType } = btn.dataset;
    const recipes = await api(`/recipes?meal_type=${encodeURIComponent(mealType)}`);
    const choice = prompt("Swap this meal for which recipe? Enter a number:\n" + recipes.map((r, i) => `${i + 1}. ${r.title}`).join("\n"));
    const picked = recipes[Number(choice) - 1];
    if (!picked) return;
    await api(`/plans/${planId}/meals/${mealId}`, { method: "PUT", body: JSON.stringify({ recipe_id: picked.id }) });
    showToast(`Swapped to ${picked.title}.`); await openPlan(planId);
  }
  const formObject = (form) => Object.fromEntries(new FormData(form).entries());
  const asNumber = (value) => Number(value || 0);
  function renderFitnessTargets(targets) {
    if (!targets) { $("#fitness-targets").innerHTML = empty("Save your profile to calculate estimated targets."); return; }
    const cards = [["Daily energy",targets.daily_kcal,"kcal"],["Protein",targets.protein_g,"g"],["Carbohydrates",targets.carbs_g,"g"],["Fat",targets.fat_g,"g"]];
    $("#fitness-targets").innerHTML = cards.map(([label,value,unit]) => `<div class="fitness-stat"><span>${esc(label)}</span><strong>${Math.round(value).toLocaleString()} <small>${unit}</small></strong></div>`).join("") + `<p class="field-help">${esc(targets.method)}. ${esc(targets.disclaimer)}</p>`;
  }
  async function loadFitness() {
    try {
      const p = await api("/fitness/profile");
      if (p.profile) {
        const fields = {age:"#fit-age",sex:"#fit-sex",height_cm:"#fit-height",weight_kg:"#fit-weight",activity_level:"#fit-activity",goal:"#fit-goal",protein_g_per_kg:"#fit-protein"};
        Object.entries(fields).forEach(([key,selector]) => { if (p.profile[key] != null) $(selector).value = p.profile[key]; });
      }
      renderFitnessTargets(p.targets);
      await loadGoalRecipes();
      await refreshFitness();
    } catch (e) { showToast(e.message,"error"); }
  }
  function renderWorkoutRow(w) {
    return `<div class="compact-row"><span class="ingredient-symbol">💪</span><div class="compact-info"><strong>${esc(w.workout_type)}</strong><small>${esc(w.workout_date)} · ${w.duration_min} min · ${esc(w.intensity)}</small></div><button class="text-button" data-delete-workout="${w.id}">Remove</button></div>`;
  }
  async function refreshFitness() {
    try {
      const [diary, summary, workouts] = await Promise.all([api("/diary"),api("/nutrition/daily"),api("/workouts?limit=8")]);
      const card = (title,row,emptyLabel = "") => `<div class="fitness-summary-card"><strong>${title}</strong>${emptyLabel ? `<span>${emptyLabel}</span><span>Add meals to your plan to see planned totals.</span>` : `<span>${nutritionNumber(row.kcal)} kcal</span><span>${nutritionNumber(row.protein_g)} g protein · ${nutritionNumber(row.carbs_g)} g carbs · ${nutritionNumber(row.fat_g)} g fat</span>`}</div>`;
      const plannedCard = Number(summary.planned?.entries) > 0
        ? card("Planned", summary.planned)
        : card("Planned", summary.planned, "No meals planned");
      $("#fitness-summary").innerHTML = plannedCard + card("Actually consumed",summary.consumed) + remainingNutritionHtml(summary.consumed, summary.targets, summary.planned);
      const micros = Object.entries(summary.consumed_micronutrients || {});
      if (micros.length) $("#fitness-summary").insertAdjacentHTML("beforeend",`<p class="field-help">Micronutrient values recorded: ${micros.map(([k,v])=>`${esc(k)} ${v}`).join(" · ")}. Facts retain source metadata in diary entries.</p>`);
      $("#food-diary-list").innerHTML = diary.length ? diary.map(d=>`<div class="compact-row"><span class="ingredient-symbol">${foodEmoji(d.item_name)}</span><div class="compact-info"><strong>${esc(d.item_name)}</strong><small>${esc(d.meal_type)} · ${d.servings} serving(s) · ${nutritionNumber(d.kcal)} kcal</small></div><button class="text-button" data-delete-diary="${d.id}">Remove</button></div>`).join("") : empty("No food logged today yet.");
      const diaryCount = $("#food-diary-count");
      if (diaryCount) diaryCount.textContent = `${diary.length} ${diary.length === 1 ? "ENTRY" : "ENTRIES"}`;
      const workoutRows = workouts.map(renderWorkoutRow).join("");
      $("#workout-list").innerHTML = workoutRows || empty("No workouts logged yet.");
    } catch(e) { showToast(e.message,"error"); }
  }
  async function showWorkoutFuel(phase) {
    const data = await api(`/workout-fuel/recommendations?phase=${phase}`);
    $("#workout-fuel-results").innerHTML = `<p class="field-help">${esc(data.guidance)}</p>` + data.recipes.map(r=>`<div class="compact-row"><span class="ingredient-symbol">${foodEmoji(r.title)}</span><div class="compact-info"><strong>${esc(r.title)}</strong><small>${r.nutrition_per_serving.kcal} kcal · ${r.nutrition_per_serving.protein_g}g protein · ${r.nutrition_per_serving.carbs_g}g carbs / serving</small></div></div>`).join("");
  }
  async function discoverExternalRecipes() {
    const q = $("#external-recipe-query").value.trim(); if (!q) return;
    const rows = await api(`/recipes/discover?q=${encodeURIComponent(q)}`);
    $("#external-recipe-results").innerHTML = rows.length ? rows.map(r=>`<div class="compact-row"><span class="ingredient-symbol">${foodEmoji(r.title)}</span><div class="compact-info"><strong>${esc(r.title)}</strong><small>${esc(r.category||"Meal")} · ${esc(r.area||"Cuisine unknown")} · TheMealDB</small></div><button class="text-button" data-import-recipe="${esc(r.title)}">Import →</button>${r.source_url?`<a class="text-button" href="${esc(r.source_url)}" target="_blank" rel="noopener">Source ↗</a>`:""}</div>`).join("") : empty("No matching external recipes found.");
  }
  async function loadPreferences() {
    try { const user = await api("/me"); state.user = user; $("#pref-diet").value = user.diet || ""; $("#pref-kcal").value = user.daily_kcal || ""; $("#pref-household").value = user.household_size || 1; }
    catch(e) { showToast(e.message,"error"); }
  }
  async function savePreferences(button) {
    const body = {diet:$("#pref-diet").value || null, daily_kcal:$("#pref-kcal").value ? Number($("#pref-kcal").value) : null, household_size:Number($("#pref-household").value || 1)};
    const result = await withBusy(button, () => api("/me",{method:"PUT",body:JSON.stringify(body)}), "Saving…");
    if (result) { state.user = result; showToast("Your preferences have been saved."); }
  }
  function togglePantryForm(show) { $("#pantry-form").classList.toggle("hidden", !show); if (show) $("#pantry-ingredient").focus(); }
  document.addEventListener("click", async (event) => {
    const authTab = event.target.closest("[data-auth-tab]");
    if (authTab) { authScreen(authTab.dataset.authTab); return; }
    const pageBtn = event.target.closest("[data-page]");
    if (pageBtn) { event.preventDefault(); navigate(pageBtn.dataset.page); return; }
    const snapshotPage = event.target.closest("[data-snapshot-page]");
    if (snapshotPage) { navigate(snapshotPage.dataset.snapshotPage); return; }
    const snapshotScroll = event.target.closest("[data-snapshot-scroll]");
    if (snapshotScroll) { document.getElementById(snapshotScroll.dataset.snapshotScroll)?.scrollIntoView({behavior:"smooth", block:"start"}); return; }
    const recipeBtn = event.target.closest("[data-recipe-open]");
    if (recipeBtn) { openRecipe(recipeBtn.dataset.recipeOpen); return; }
    const rescaleBtn = event.target.closest("[data-rescale-recipe]");
    if (rescaleBtn) { const n = Number($("#modal-servings").value); if (!Number.isInteger(n) || n < 1 || n > 24) { showToast("Choose between 1 and 24 servings.", "error"); return; } openRecipe(rescaleBtn.dataset.rescaleRecipe, n); return; }
    const planBtn = event.target.closest("[data-plan-open]");
    if (planBtn) { openPlan(planBtn.dataset.planOpen); return; }
    if (event.target.closest("[data-close-modal]")) { $("#recipe-modal").classList.add("hidden"); return; }
    if (event.target.closest("#show-pantry-form") || event.target.closest("#empty-add-pantry")) { togglePantryForm(true); return; }
    if (event.target.closest("#hide-pantry-form") || event.target.closest("#cancel-pantry")) { togglePantryForm(false); return; }
    const del = event.target.closest("[data-delete-pantry]");
    if (del) {
      if (!confirm("Remove this ingredient from your pantry?")) return;
      try { await api(`/pantry/${encodeURIComponent(del.dataset.deletePantry)}`, { method: "DELETE" }); await loadPantry(); showToast("Ingredient removed."); }
      catch (e) { showToast(e.message, "error"); }
      return;
    }
    const edit = event.target.closest("[data-edit-pantry]");
    if (edit) {
      const value = prompt("How much is left? (use the unit shown, e.g. 250 for 250 g; 0 marks it used up)");
      if (value === null || value.trim() === "" || Number.isNaN(Number(value))) return;
      try { await api(`/pantry/${edit.dataset.editPantry}`, { method: "PATCH", body: JSON.stringify({ amount: Number(value) }) }); await loadPantry(); showToast("Pantry updated."); }
      catch (e) { showToast(e.message, "error"); }
      return;
    }
    const delPlan = event.target.closest("[data-plan-delete]");
    if (delPlan) {
      if (!confirm("Delete this saved plan? Your pantry is not changed.")) return;
      try {
        const deletedId = String(delPlan.dataset.planDelete);
        await api(`/plans/${deletedId}`, { method: "DELETE" });
        const openPlanBadge = $("#plan-result")?.querySelector(".small-badge");
        if (openPlanBadge?.textContent.includes(`PLAN #${deletedId}`)) $("#plan-result").classList.add("hidden");
        await Promise.all([loadPlans(), loadDashboard()]);
        showToast("Saved plan deleted.");
      } catch (e) { showToast(e.message, "error"); }
      return;
    }
    const cook = event.target.closest("[data-cook-meal]");
    if (cook) {
      if (!confirm("Mark as cooked? The ingredients will be deducted from your pantry.")) return;
      try { await api(`/plans/${cook.dataset.planId}/meals/${cook.dataset.cookMeal}/cook`, { method: "POST" }); showToast("Cooked. Pantry updated."); await openPlan(cook.dataset.planId); }
      catch (e) { showToast(e.message, "error"); }
      return;
    }
    const swap = event.target.closest("[data-swap-meal]");
    if (swap) { swapMeal(swap).catch(e => showToast(e.message, "error")); return; }
    const fav = event.target.closest("[data-favorite-toggle]");
    if (fav) {
      const active = fav.dataset.active === "true";
      try { const result = await api(`/recipes/${fav.dataset.favoriteToggle}/feedback`, {method:"PUT", body:JSON.stringify({favorite:!active})});
        fav.dataset.active = String(result.favorite); fav.setAttribute("aria-pressed", String(result.favorite)); fav.textContent = result.favorite ? "♥ Favourite" : "♡ Favourite";
        await loadFavorites(); showToast(result.favorite ? "Added to favourites." : "Removed from favourites.");
      } catch(e) { showToast(e.message,"error"); }
      return;
    }
    const unfav = event.target.closest("[data-unfavorite]");
    if (unfav) {
      try { await api(`/recipes/${unfav.dataset.unfavorite}/feedback`, {method:"PUT", body:JSON.stringify({favorite:false})}); await loadFavorites(); showToast("Removed from favourites."); }
      catch(e) { showToast(e.message,"error"); }
      return;
    }
    if (event.target.closest("[data-search-external]")) { loadRecipes({ external: true }); return; }
  });
  document.addEventListener("keydown", event => {
    if ((event.key === "Enter" || event.key === " ") && event.target.matches("[data-snapshot-page], [data-snapshot-scroll]")) {
      event.preventDefault(); event.target.click();
    }
  });
  document.addEventListener("change", async event => {
    if (!event.target.matches("[data-recipe-rating]")) return;
    const select = event.target;
    if (!select.value) return;
    try {
      await api(`/recipes/${select.dataset.recipeRating}/feedback`, {method:"PUT", body:JSON.stringify({rating:Number(select.value)})});
      showToast(`Rating saved: ${select.value}/5.`);
      await loadFavorites();
    } catch (e) { showToast(e.message, "error"); }
  });
  $("#auth-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const button = $("#auth-submit");
    const body = {email:$("#auth-email").value.trim(),password:$("#auth-password").value};
    const result = await withBusy(button, async () => {
      if (state.authMode === "register") {
        await api("/auth/register",{method:"POST",body:JSON.stringify(body)});
        showToast("Account created. Signing you in…");
      }
      const login = await api("/auth/login",{method:"POST",body:JSON.stringify(body)});
      state.token = login.access_token; localStorage.setItem("mealmate_token",state.token);
      const user = await api("/me");
      if (user?.email) localStorage.setItem("mealmate_email", user.email);
      enterApp(user); return user;
    }, "Connecting…");
    if (result) $("#auth-password").value = "";
  });
  $("#logout-button").addEventListener("click", () => logout());
  $("#profile-button").addEventListener("click", () => navigate("preferences"));
  $("#mobile-menu").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
  $("#show-pantry-form").addEventListener("click", () => togglePantryForm(true));
  $("#pantry-form").addEventListener("submit", async (event) => {
      event.preventDefault();

      const form = event.currentTarget;
      const button = $('button[type="submit"]', form);

      const body = {
          ingredient: $("#pantry-ingredient").value.trim(),
          amount: Number($("#pantry-amount").value)
      };

      if ($("#pantry-unit").value) {
          body.unit = $("#pantry-unit").value;
      }

      if ($("#pantry-expiry").value) {
          body.expires_on = $("#pantry-expiry").value;
      }

      const result = await withBusy(
          button,
          () => api("/pantry", {
              method: "POST",
              body: JSON.stringify(body)
          }),
          "Saving…"
      );

      if (result) {
          form.reset();
          togglePantryForm(false);
          await loadPantry();
          if (result.created_new) {
              const hint = result.similar?.length ? ` Did you mean: ${result.similar.join(", ")}?` : "";
              showToast(`“${result.ingredient}” is not in the recipe catalog yet, so no recipe will use it.${hint}`, "error");
          } else showToast(result.matched_as ? `Added as “${result.matched_as}”.` : "Ingredient added to your pantry.");
      }
  });
  $("#pantry-search").addEventListener("input", renderPantry);
  $("#refresh-pantry-recipes")?.addEventListener("click", () => loadPantryRecommendations().catch(e => showToast(e.message, "error")));
  $("#apply-recipe-filters").addEventListener("click", () => loadRecipes());
  $("#refresh-favourites")?.addEventListener("click", () => loadFavorites());
  $("#recipe-sort").addEventListener("change", () => loadRecipes());
  $("#recipe-search").addEventListener("keydown", e => { if(e.key === "Enter"){e.preventDefault();loadRecipes();} });
    $("#plan-form").addEventListener("submit", e => { e.preventDefault(); generatePlan($('button[type="submit"]',e.currentTarget)); });
  $("#preferences-form").addEventListener("submit", e => { e.preventDefault(); savePreferences($('button[type="submit"]',e.currentTarget)); });
  $("#recipe-modal").addEventListener("keydown", e => { if(e.key==="Escape") $("#recipe-modal").classList.add("hidden"); });
  document.addEventListener("keydown", e => { if(e.key==="Escape"){ $("#recipe-modal").classList.add("hidden"); $("#sidebar").classList.remove("open"); } });
  $("#fitness-profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    const body = formObject(event.currentTarget);

    ["age"].forEach((key) => {
      body[key] = asNumber(body[key]);
    });

    ["height_cm", "weight_kg", "protein_g_per_kg"].forEach((key) => {
      body[key] = asNumber(body[key]);
    });

    const result = await withBusy(
      $('button[type="submit"]', event.currentTarget),
      () =>
        api("/fitness/profile", {
          method: "PUT",
          body: JSON.stringify(body),
        }),
      "Calculating…"
    );

    if (result) {
      renderFitnessTargets(result.targets);

      // Refresh recommendations and nutrition totals immediately.
      await Promise.all([loadGoalRecipes(), refreshFitness()]);

      showToast(
        "Fitness targets saved. Your meal ideas and nutrition summary are updated."
      );
    }
  });

  $("#food-diary-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submitButton = $('button[type="submit"]', form);
    const body = formObject(form);

    ["servings", "kcal", "protein_g", "carbs_g", "fat_g"].forEach((key) => {
      body[key] = asNumber(body[key]);
    });

    const result = await withBusy(
      submitButton,
      () =>
        api("/diary", {
          method: "POST",
          body: JSON.stringify(body),
        }),
      "Logging…"
    );

    if (result) {
      form.reset();
      $("#diary-meal").value = "";
      $("#diary-servings").value = "1";
      ["diary-kcal", "diary-protein", "diary-carbs", "diary-fat"].forEach((id) => { $(`#${id}`).value = "0"; });
      await refreshFitness();
      showToast("Food logged as consumed.");
    }
  });

  $("#workout-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    // Capture the form before awaiting: event.currentTarget is cleared after the event callback returns.
    const form = event.currentTarget;
    const submitButton = $('button[type="submit"]', form);
    const body = formObject(form);
    body.duration_min = asNumber(body.duration_min);

    const result = await withBusy(
      submitButton,
      () => api("/workouts", {
        method: "POST",
        body: JSON.stringify(body),
      }),
      "Saving…"
    );

    if (!result) return;

    form.reset();
    $("#workout-duration").value = 45;
    $("#workout-intensity").value = "moderate";

    // Render the server-confirmed workout immediately.
    const list = $("#workout-list");
    if (list && result.id != null) {
      const existing = list.querySelector(`[data-delete-workout="${result.id}"]`);
      if (!existing) {
        if (list.querySelector(".empty-state, .empty-inline")) list.innerHTML = "";
        list.insertAdjacentHTML("afterbegin", renderWorkoutRow(result));
      }
    }

    // Refresh from the API after rendering so the log remains synchronized with the database.
    await refreshFitness();
    await loadGoalRecipes();
    showToast("Workout saved. Your activity log and meal ideas are refreshed.");
  });

  $("#fitness-refresh").addEventListener("click", refreshFitness);

  $("#pre-fuel").addEventListener("click", () => {
    showWorkoutFuel("pre").catch((error) =>
      showToast(error.message, "error")
    );
  });

  $("#post-fuel").addEventListener("click", () => {
    showWorkoutFuel("post").catch((error) =>
      showToast(error.message, "error")
    );
  });
  
  document.addEventListener("click",async event=>{
    const diary=event.target.closest("[data-delete-diary]"); if(diary){try{await api(`/diary/${diary.dataset.deleteDiary}`,{method:"DELETE"});await refreshFitness();showToast("Diary entry removed.");}catch(e){showToast(e.message,"error");}return;}
    const workout=event.target.closest("[data-delete-workout]"); if(workout){try{await api(`/workouts/${workout.dataset.deleteWorkout}`,{method:"DELETE"});await refreshFitness();showToast("Workout removed.");}catch(e){showToast(e.message,"error");}return;}
    const recipe=event.target.closest("[data-import-recipe]"); if(recipe){try{const data=await api(`/recipes/import?name=${encodeURIComponent(recipe.dataset.importRecipe)}`,{method:"POST"});showToast(`Imported recipe ID(s): ${data.imported_recipe_ids.join(", ")}. Nutrition may be incomplete.`);}catch(e){showToast(e.message,"error");}return;}
  });
  $("#toggle-password")?.addEventListener("click", () => {
    const input = $("#auth-password");
    const button = $("#toggle-password");
    if (!input || !button) return;

    const showPassword = input.type === "password";
    input.type = showPassword ? "text" : "password";
    button.innerHTML = showPassword
      ? `<svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c6.4 0 10 7 10 7a16.6 16.6 0 0 1-4 4.8"/><path d="M6.6 6.6C3.6 8.5 2 12 2 12s3.6 7 10 7a10.8 10.8 0 0 0 4-.8"/></svg>`
      : `<svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>`;
    const label = showPassword ? "Hide password" : "Show password";
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
    button.setAttribute("aria-pressed", String(showPassword));
  });

  restoreSession();
})();