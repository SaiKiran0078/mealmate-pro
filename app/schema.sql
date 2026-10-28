-- MealMate schema (SQLite). Quantities are stored in each ingredient's base unit (g / ml / pcs).

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT NOT NULL,
    daily_kcal      INTEGER,
    diet            TEXT,
    household_size  INTEGER NOT NULL DEFAULT 1 CHECK (household_size BETWEEN 1 AND 12),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ingredients (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE COLLATE NOCASE,
    base_unit         TEXT NOT NULL CHECK (base_unit IN ('g', 'ml', 'pcs')),
    category          TEXT NOT NULL DEFAULT 'other',
    is_staple         INTEGER NOT NULL DEFAULT 0,
    density_g_per_ml  REAL NOT NULL DEFAULT 1.0 CHECK (density_g_per_ml > 0),
    grams_per_piece   REAL,
    kcal_per_100g     REAL NOT NULL DEFAULT 0,
    protein_per_100g  REAL NOT NULL DEFAULT 0,
    carbs_per_100g    REAL NOT NULL DEFAULT 0,
    fat_per_100g      REAL NOT NULL DEFAULT 0,
    nutrition_known   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS recipes (
    id           INTEGER PRIMARY KEY,
    owner_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,  -- NULL = shared catalog
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    cuisine      TEXT NOT NULL DEFAULT 'other',
    meal_types   TEXT NOT NULL,                                   -- comma separated
    servings     INTEGER NOT NULL CHECK (servings > 0),
    prep_min     INTEGER NOT NULL DEFAULT 0,
    cook_min     INTEGER NOT NULL DEFAULT 0,
    difficulty   TEXT NOT NULL DEFAULT 'easy' CHECK (difficulty IN ('easy', 'medium', 'hard')),
    diet_tags    TEXT NOT NULL DEFAULT '',                        -- comma separated
    source       TEXT NOT NULL DEFAULT 'user',                    -- seed | themealdb | user
    external_id  TEXT,
    image_url    TEXT,
    UNIQUE (source, external_id)
);

-- Many-to-many: a recipe has many ingredients, an ingredient appears in many recipes.
CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_id      INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    ingredient_id  INTEGER NOT NULL REFERENCES ingredients(id),
    quantity       REAL NOT NULL CHECK (quantity > 0),
    note           TEXT NOT NULL DEFAULT '',
    optional       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (recipe_id, ingredient_id)
);

CREATE TABLE IF NOT EXISTS recipe_steps (
    recipe_id     INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    step_no       INTEGER NOT NULL,
    instruction   TEXT NOT NULL,
    duration_min  INTEGER,
    tip           TEXT,
    passive       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (recipe_id, step_no)
);

-- One row per purchase ("batch") so every batch can have its own expiry date.
-- One row per purchase ("batch") so every batch can have its own expiry date.
-- quantity is normalized to the ingredient's base unit.
-- entered_amount and entered_unit preserve the user's original input.

CREATE TABLE IF NOT EXISTS pantry_items (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ingredient_id   INTEGER NOT NULL REFERENCES ingredients(id),
    quantity        REAL NOT NULL CHECK (quantity >= 0),
    entered_amount  REAL,
    entered_unit    TEXT,
    expires_on      TEXT,
    added_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pantry_user_ingredient
    ON pantry_items (user_id, ingredient_id);
    
CREATE TABLE IF NOT EXISTS meal_plans (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_date  TEXT NOT NULL,
    days        INTEGER NOT NULL,
    servings    INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS planned_meals (
    id         INTEGER PRIMARY KEY,
    plan_id    INTEGER NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,
    meal_date  TEXT NOT NULL,
    meal_type  TEXT NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
    recipe_id  INTEGER NOT NULL REFERENCES recipes(id),
    servings   INTEGER NOT NULL,
    cooked     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (plan_id, meal_date, meal_type)
);

-- Fitness profile and measurable nutrition goals.
CREATE TABLE IF NOT EXISTS fitness_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    age INTEGER CHECK (age BETWEEN 13 AND 100),
    sex TEXT CHECK (sex IN ('female','male','other')),
    height_cm REAL CHECK (height_cm BETWEEN 100 AND 250),
    weight_kg REAL CHECK (weight_kg BETWEEN 25 AND 350),
    activity_level TEXT NOT NULL DEFAULT 'moderate' CHECK (activity_level IN ('sedentary','light','moderate','active','very_active')),
    goal TEXT NOT NULL DEFAULT 'maintenance' CHECK (goal IN ('fat_loss','muscle_gain','maintenance','general_health')),
    protein_g_per_kg REAL NOT NULL DEFAULT 1.6 CHECK (protein_g_per_kg BETWEEN 0.8 AND 2.5),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Food diary: records consumed food separately from planned meals.
CREATE TABLE IF NOT EXISTS food_diary (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consumed_on TEXT NOT NULL,
    meal_type TEXT NOT NULL CHECK (meal_type IN ('breakfast','lunch','dinner','snack')),
    item_name TEXT NOT NULL,
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
    servings REAL NOT NULL DEFAULT 1 CHECK (servings > 0 AND servings <= 50),
    kcal REAL NOT NULL DEFAULT 0 CHECK (kcal >= 0),
    protein_g REAL NOT NULL DEFAULT 0 CHECK (protein_g >= 0),
    carbs_g REAL NOT NULL DEFAULT 0 CHECK (carbs_g >= 0),
    fat_g REAL NOT NULL DEFAULT 0 CHECK (fat_g >= 0),
    micros_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','recipe','planned')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_food_diary_user_date ON food_diary(user_id, consumed_on);

CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workout_date TEXT NOT NULL,
    workout_type TEXT NOT NULL,
    duration_min INTEGER NOT NULL CHECK (duration_min BETWEEN 1 AND 1440),
    intensity TEXT NOT NULL DEFAULT 'moderate' CHECK (intensity IN ('light','moderate','vigorous')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_workouts_user_date ON workouts(user_id, workout_date);

-- Micronutrient facts are only shown when sourced; no fabricated defaults.
CREATE TABLE IF NOT EXISTS ingredient_nutrients (
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    nutrient_key TEXT NOT NULL,
    amount_per_100g REAL NOT NULL CHECK (amount_per_100g >= 0),
    unit TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_id TEXT,
    PRIMARY KEY (ingredient_id, nutrient_key)
);

-- Per-user recipe feedback; one rating and favourite flag per recipe/account.
CREATE TABLE IF NOT EXISTS recipe_feedback (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    is_favorite INTEGER NOT NULL DEFAULT 0 CHECK (is_favorite IN (0, 1)),
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, recipe_id)
);
