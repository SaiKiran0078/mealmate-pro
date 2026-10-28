/* Pure HTML-building helpers for MealMate (no DOM access, no network) so they can be unit-tested with Node.
 * Browser: exposed as window.MealMateRender.  Node: module.exports. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.MealMateRender = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const EMOJI = [["chicken","🍗"],["egg","🥚"],["tomato","🍅"],["potato","🥔"],["rice","🍚"],["spinach","🥬"],["lettuce","🥬"],["salad","🥗"],["pasta","🍝"],["noodle","🍜"],["fish","🐟"],["salmon","🐟"],["tuna","🐟"],["bread","🍞"],["toast","🍞"],["cheese","🧀"],["paneer","🧀"],["milk","🥛"],["apple","🍎"],["banana","🍌"],["carrot","🥕"],["pepper","🫑"],["onion","🧅"],["garlic","🧄"],["bean","🫘"],["lentil","🫘"],["chickpea","🫘"],["soup","🍲"],["curry","🍛"],["wrap","🌯"],["sandwich","🥪"],["pancake","🥞"],["oat","🥣"],["yogurt","🥣"],["beef","🥩"],["mushroom","🍄"],["broccoli","🥦"],["avocado","🥑"],["lemon","🍋"],["orange","🍊"]];
  const foodEmoji = (name = "") => { const n = String(name).toLowerCase(); return (EMOJI.find(([k]) => n.includes(k)) || [null, "🥗"])[1]; };

  // Dish-specific food photography. Specific dish patterns must come before broad ingredient matches.
  const mealPhoto = (name = "", type = "") => {
    const n = `${name} ${type}`.toLowerCase();
    const photos = [
      [/quesadilla|tortilla/, "photo-1618040996337-56904b7850b9"],
      [/omelette|scramble|fried egg|egg toast|egg sandwich/, "photo-1525351484163-7529414344d8"],
      [/paneer|butter chicken|chicken curry|curry|biryani|masala/, "photo-1603894584373-5ac82b2ae398"],
      [/pancake|waffle|french toast/, "photo-1528207776546-365bb710ee93"],
      [/pasta|spaghetti|macaroni|noodle/, "photo-1473093295043-cdd812d0e601"],
      [/salad|spinach|lettuce|broccoli|vegetable|veggie/, "photo-1512621776951-a57141f2eefd"],
      [/chicken|stir.?fry/, "photo-1547592180-85f173990554"],
      [/fish|salmon|tuna|seafood/, "photo-1519708227418-c8fd9a32b7a2"],
      [/soup|stew|lentil|dal|bean|chickpea/, "photo-1547592166-23ac45744acd"],
      [/wrap|sandwich|burger|toast/, "photo-1528735602780-2552fd46c7af"],
      [/fruit|yogurt|oat|smoothie/, "photo-1490474418585-ba9bad8fd0ea"],
      [/egg|breakfast/, "photo-1525351484163-7529414344d8"]
    ];
    const found = photos.find(([re]) => re.test(n));
    const id = found ? found[1] : "photo-1546069901-ba9599a7e63c";
    return `https://images.unsplash.com/${id}?auto=format&fit=crop&w=640&h=320&q=78`;
  };

  const parseDay = (v) => { const d = new Date(`${v}T00:00:00`); return Number.isNaN(d.getTime()) ? null : d; };
  const fmtDate = (v) => { if (!v) return ""; const d = parseDay(v); return d ? d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : String(v); };
  const fmtDay = (v) => { const d = parseDay(v); return d ? d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) : String(v || ""); };
  const num = (v) => Math.round(Number(v) || 0);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
  const empty = (text) => `<div class="empty-inline">${esc(text)}</div>`;

  /* ---------- overview ---------- */
  function overviewStats(d) {
    const p = d.pantry || {}, r = d.recipes || {}, pl = d.plans || {};
    return {
      ingredients: p.ingredients ?? 0,
      ingredientsNote: p.batches != null ? `${plural(p.batches, "batch", "batches")} in stock` : "Ingredients on hand",
      expiring: (p.expiring_soon || []).length,
      expiringNote: (p.expired || []).length ? `${(p.expired || []).length} already past date` : "Worth using in 3 days",
      ready: r.ready_to_cook ?? 0,
      readyNote: r.almost_ready ? `+${r.almost_ready} almost ready` : "Recipes you can cook right now",
      plans: pl.count ?? 0,
    };
  }

  function expiryRowHtml(item, expired) {
    const name = item.name || "Ingredient";
    const tag = expired
      ? `<span class="expiry-tag expired">Expired ${esc(fmtDate(item.expires_on))}</span>`
      : `<span class="expiry-tag">${item.days_left === 0 ? "Today" : item.days_left === 1 ? "Tomorrow" : `In ${esc(item.days_left)} days`}</span>`;
    return `<div class="compact-row"><span class="ingredient-symbol">${foodEmoji(name)}</span><div class="compact-info"><strong>${esc(name)}</strong><small>${esc(item.display || "")}</small></div>${tag}</div>`;
  }

  function useSoonHtml(pantry) {
    const soon = pantry.expiring_soon || [], gone = pantry.expired || [];
    if (!soon.length && !gone.length) return empty("Nothing expiring soon. Nice work!");
    return soon.slice(0, 4).map((i) => expiryRowHtml(i, false)).join("") + gone.slice(0, 3).map((i) => expiryRowHtml(i, true)).join("");
  }

  /* ---------- recipes ---------- */
  function badgeFor(m) {
    if (m.status === "ready" || m.can_cook_now) return { cls: "ready", text: "Ready to cook" };
    if (m.coverage_pct != null) return { cls: m.status === "almost" ? "almost" : "partial", text: `${m.coverage_pct}% of your pantry` };
    return { cls: "idea", text: "Recipe idea" };
  }

  function recipeCardHtml(item) {
    const r = item.recipe || item, b = badgeFor(item);
    const missing = (item.missing || []).map((x) => x.name);
    const missText = missing.length ? `<p class="recipe-missing">Missing: ${esc(missing.slice(0, 4).join(", "))}${missing.length > 4 ? ` +${missing.length - 4}` : ""}</p>` : "";
    const n = r.nutrition_per_serving;
    const nutrition = n ? `<span title="per serving">${esc(n.kcal)} kcal · ${esc(n.protein_g)} g protein${r.nutrition_complete === false ? " (partial data)" : ""}</span>` : "";
    const why = (item.why || [])[1] ? `<p class="recipe-why">${esc(item.why[1])}</p>` : "";
    return `<article class="recipe-card"><div class="recipe-art"><span class="small-badge">${esc(r.meal_types?.[0] || r.cuisine || "MEAL")}</span><span class="recipe-emoji">${foodEmoji(r.title)}</span></div><div class="recipe-card-body"><h3>${esc(r.title)}</h3><p class="recipe-description">${esc(r.description || "Open the recipe to see ingredients and cooking steps.")}</p><div class="recipe-meta"><span>◷ ${esc(r.total_min ?? 0)} min</span><span>♧ ${esc(r.difficulty || "easy")}</span><span>♙ ${esc(r.servings || 1)} servings</span>${nutrition}</div>${missText}${why}<div class="recipe-card-footer"><span class="match-badge ${b.cls}">${esc(b.text)}</span><button data-recipe-open="${esc(r.id)}">View recipe →</button></div><div class="recipe-feedback-controls"><button class="text-button" data-favorite-toggle="${esc(r.id)}" data-active="false" aria-pressed="false">♡ Favourite</button><label class="recipe-rating">Rate <select data-recipe-rating="${esc(r.id)}" aria-label="Rate ${esc(r.title)}"><option value="">—</option><option value="1">★ 1</option><option value="2">★ 2</option><option value="3">★ 3</option><option value="4">★ 4</option><option value="5">★ 5</option></select></label></div></div></article>`;
  }

  function interpretedHtml(i) {
    if (!i || !(i.notes || []).length) return "";
    const chips = [...(i.meal_type ? [i.meal_type] : []), ...(i.diet ? [String(i.diet).replace("_", " ")] : []), ...i.notes];
    return `<div class="search-chips" aria-label="How your search was understood">${chips.map((c) => `<span class="chip">${esc(c)}</span>`).join("")}</div>`;
  }

  function externalRowHtml(m) {
    return `<div class="compact-row"><span class="ingredient-symbol">${foodEmoji(m.title)}</span><div class="compact-info"><strong>${esc(m.title)}</strong><small>${esc(m.category || "Meal")} · ${esc(m.area || "")} · from TheMealDB</small></div><button class="text-button" data-import-recipe="${esc(m.title)}">Import →</button></div>`;
  }

  function searchResultsHtml(res) {
    const hasLocal = (res.results || []).length > 0;
    let html = interpretedHtml(res.interpreted);
    if (hasLocal) html += `<div class="recipe-grid">${res.results.map(recipeCardHtml).join("")}</div>`;
    else {
      html += `<div class="empty-state"><span>♨</span><h3>No recipes matched “${esc(res.query)}”</h3><p>Nothing unrelated is shown on purpose.</p>${(res.suggestions || []).map((s) => `<p class="field-help">${esc(s)}</p>`).join("")}<button class="btn btn-outline" data-search-external="1">Search TheMealDB</button></div>`;
      if ((res.related || []).length) html += `<div class="section-heading"><div><span class="eyebrow">PARTIAL MATCHES</span><h2>Related to part of your search</h2></div></div><div class="recipe-grid">${res.related.map(recipeCardHtml).join("")}</div>`;
    }
    if (res.external_error) html += `<div class="notice notice-warm"><span>!</span><div><strong>TheMealDB is unavailable.</strong><p>${esc(res.external_error)}</p></div></div>`;
    if ((res.external || []).length) html += `<div class="section-heading"><div><span class="eyebrow">FROM THEMEALDB</span><h2>More dishes online</h2></div></div><div class="compact-list">${res.external.map(externalRowHtml).join("")}</div>`;
    return html;
  }

  /* ---------- pantry ---------- */
  function pantryCardHtml(item) {
    const name = item.name || "Ingredient";
    const status = item.status;
    const expiry = status === "no_expiry" || !item.expires_on ? "No expiry date set"
      : status === "expired" ? `Expired · ${fmtDate(item.expires_on)}`
      : status === "expiring" ? `◷ Use soon · ${fmtDate(item.expires_on)}`
      : `Expiry · ${fmtDate(item.expires_on)}`;
    const added = item.entered_amount != null && item.entered_unit ? `<small class="pantry-added">Added as ${esc(item.entered_amount)} ${esc(item.entered_unit)}</small>` : "";
    return `<article class="pantry-item ${status === "expired" ? "is-expired" : ""}"><div class="pantry-item-top"><span class="ingredient-symbol">${foodEmoji(name)}</span><span><button class="text-button" data-edit-pantry="${esc(item.id)}" title="Correct the remaining amount" aria-label="Edit ${esc(name)}">Edit</button><button class="delete-item" data-delete-pantry="${esc(item.id)}" title="Remove ingredient" aria-label="Remove ${esc(name)}">×</button></span></div><h3>${esc(name)}</h3><div class="pantry-quantity">${esc(item.display)}</div>${added}<div class="pantry-expiry ${status === "expiring" || status === "expired" ? "expiring" : ""}">${esc(expiry)}</div></article>`;
  }

  /* ---------- meal plans ---------- */
  function savedPlanRowHtml(p) {
    const label = `${plural(p.days, "day")} from ${fmtDate(p.start_date)}`;
    return `<div class="saved-plan-row"><div><strong>${esc(label)}</strong><small>${esc(plural(p.meals, "meal"))} · ${esc(p.cooked)} cooked · ${esc(p.servings)} serving${p.servings === 1 ? "" : "s"}</small></div><div class="saved-plan-actions"><button data-plan-open="${esc(p.id)}">Open →</button><button class="text-button danger" data-plan-delete="${esc(p.id)}" aria-label="Delete saved plan from ${esc(label)}">Delete</button></div></div>`;
  }

  function mealRowHtml(m, planId) {
    const n = m.nutrition_per_serving || {};
    const hasIds = planId != null && m.meal_id != null;
    const state = m.cooked ? `<span class="small-badge">COOKED</span>`
      : hasIds ? `<button class="text-button" data-cook-meal="${esc(m.meal_id)}" data-plan-id="${esc(planId)}">Mark cooked</button><button class="text-button" data-swap-meal="${esc(m.meal_id)}" data-plan-id="${esc(planId)}" data-meal-type="${esc(m.meal_type)}">Swap</button>` : "";
    const feedback = m.recipe_id != null ? `<div class="recipe-feedback-controls plan-recipe-feedback"><button class="text-button" data-favorite-toggle="${esc(m.recipe_id)}" data-active="false" aria-pressed="false">♡ Favourite</button><label class="recipe-rating">Rate <select data-recipe-rating="${esc(m.recipe_id)}" aria-label="Rate ${esc(m.title)}"><option value="">—</option><option value="1">★ 1</option><option value="2">★ 2</option><option value="3">★ 3</option><option value="4">★ 4</option><option value="5">★ 5</option></select></label></div>` : "";
    const missing = (m.missing || []).length ? `<small class="plan-missing">Need: ${esc(m.missing.join(", "))}</small>` : "";
    const photo = mealPhoto(m.title, m.meal_type);
    const completed = Boolean(m.cooked);
    return `<article class="plan-meal ${completed ? "is-cooked" : ""}"><div class="plan-meal-art"><img class="plan-meal-photo" src="${photo}" alt="Food inspiration for ${esc(m.title)}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.classList.add('is-visible')"><span class="plan-meal-emoji ${completed ? "" : "photo-fallback"}" aria-hidden="true">${foodEmoji(m.title)}</span><span class="plan-meal-type">${esc(m.meal_type)}</span>${completed ? `<span class="cooked-ribbon">✓ Cooked</span>` : `<span class="meal-photo-shade"></span>`}</div><div class="plan-meal-content"><button class="link-title" data-recipe-open="${esc(m.recipe_id)}"><strong>${esc(m.title)}</strong><span class="meal-open-arrow" aria-hidden="true">↗</span></button><div class="plan-meal-metrics"><span><b>◷</b>${esc(m.total_min ?? 0)} min</span><span><b>⚡</b>${num(n.kcal)} kcal</span><span><b>↗</b>${esc(n.protein_g ?? 0)} g protein</span></div>${missing}<span class="plan-meal-actions">${state}</span>${feedback}</div></article>`;
  }

  /* plan = response of POST /plans/generate or GET /plans/{id}; opts.grocery overrides plan.grocery_list */
  function planHtml(plan, opts = {}) {
    const days = Array.isArray(plan.days) ? plan.days : [];
    const planId = plan.plan_id ?? null;
    const grocery = opts.grocery || plan.grocery_list || [];
    const avg = plan.average_daily_nutrition?.totals?.kcal;
    const summary = [plural(days.length, "day"), ...(avg != null ? [`avg ${num(avg)} kcal/day`] : []), ...(plan.servings ? [`${plan.servings} servings`] : [])];
    const saved = planId != null
      ? `<span class="small-badge">SAVED · PLAN #${esc(planId)}</span>`
      : `<span class="small-badge badge-warn">NOT SAVED</span>`;
    const dayHtml = days.map((d) => {
      const t = d.nutrition?.totals || {};
      const pct = d.nutrition?.percent_of_target;
      const totals = `<span class="day-total">${num(t.kcal)} kcal · ${esc(t.protein_g ?? 0)} g protein${pct != null ? ` · ${esc(pct)}% of target` : ""}</span>`;
      return `<div class="plan-day"><h4>${esc(fmtDay(d.date))} ${totals}</h4><div class="plan-meals">${(d.meals || []).map((m) => mealRowHtml(m, planId)).join("") || empty("No meal fits these settings.")}</div></div>`;
    }).join("");
    const warnings = (plan.warnings || []).length ? `<div class="notice notice-warm"><span>!</span><div><strong>Worth knowing</strong>${plan.warnings.map((w) => `<p>${esc(w)}</p>`).join("")}</div></div>` : "";
    const shop = grocery.length
      ? `<div class="modal-section"><h3>Shopping list</h3><div class="ingredient-list">${grocery.map((i) => `<div class="ingredient-line">${esc(i.name)} · ${esc(i.display ?? i.quantity)}</div>`).join("")}</div></div>`
      : `<div class="modal-section"><h3>Shopping list</h3>${empty("Nothing to buy: your pantry covers this plan.")}</div>`;
    const remove = planId != null ? `<button class="text-button danger" data-plan-delete="${esc(planId)}">Delete plan</button>` : "";
    const mealCount = days.reduce((sum, d) => sum + (d.meals || []).length, 0);
    const cookedCount = days.reduce((sum, d) => sum + (d.meals || []).filter(m => m.cooked).length, 0);
    const progress = mealCount ? Math.round(cookedCount / mealCount * 100) : 0;
    return `<section class="plan-hero"><div class="plan-hero-copy"><span class="eyebrow">${planId != null ? "YOUR PERSONAL MEAL PLAN" : "YOUR FRESHLY BUILT PLAN"}</span><h3>Good food. Better days.</h3><p>Balanced ideas built around your kitchen, one delicious meal at a time.</p><div class="plan-hero-chips"><span>✦ Pantry-aware picks</span><span>♡ Nutrition at a glance</span></div></div><div class="plan-hero-art" aria-hidden="true"><span>🥗</span><i>🍅</i><b>🥑</b></div></section><div class="plan-toolbar"><div><span class="eyebrow">YOUR PLAN AT A GLANCE</span><div class="plan-summary">${summary.map((s) => `<span>${esc(s)}</span>`).join("")}</div></div><div class="plan-progress"><div><strong>${cookedCount} of ${mealCount}</strong><small>meals cooked</small></div><div class="plan-progress-track"><span style="width:${progress}%"></span></div></div></div>${warnings}<div class="plan-days-heading"><div><span class="eyebrow">THE MENU</span><h3>Your week, plated</h3></div><span class="plan-days-note">${mealCount} planned meals · mark each one as you go</span></div>${dayHtml || empty("This plan has no meals.")}${shop}`;
  }

  return { esc, foodEmoji, fmtDate, fmtDay, overviewStats, useSoonHtml, expiryRowHtml, recipeCardHtml, searchResultsHtml, interpretedHtml, pantryCardHtml, savedPlanRowHtml, planHtml, badgeFor, empty };
});
