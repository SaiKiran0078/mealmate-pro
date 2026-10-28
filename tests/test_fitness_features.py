from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@contextmanager
def make_client(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "features.db"), jwt_secret="test-secret-key-long-enough-for-hs256-signing", seed_on_startup=True))
    with TestClient(app) as client:
        registered = client.post("/auth/register", json={"email": "fitness@example.com", "password": "strong-password"})
        assert registered.status_code == 201
        token = client.post("/auth/login", json={"email": "fitness@example.com", "password": "strong-password"}).json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client


def test_profile_targets_and_food_diary(tmp_path):
    with make_client(tmp_path) as client:
        profile = client.put("/fitness/profile", json={
            "age": 28, "sex": "male", "height_cm": 178, "weight_kg": 76,
            "activity_level": "moderate", "goal": "muscle_gain", "protein_g_per_kg": 1.8,
        })
        assert profile.status_code == 200, profile.text
        targets = profile.json()["targets"]
        assert targets["daily_kcal"] > targets["maintenance_kcal"]
        assert targets["protein_g"] == 137
        logged = client.post("/diary", json={"item_name": "Test oats", "meal_type": "breakfast", "servings": 2,
                                              "kcal": 150, "protein_g": 5, "carbs_g": 25, "fat_g": 3})
        assert logged.status_code == 201, logged.text
        daily = client.get("/nutrition/daily").json()
        assert daily["consumed"]["kcal"] == 300
        assert daily["consumed"]["protein_g"] == 10
        assert daily["planned"]["kcal"] == 0


def test_workout_and_recipe_discovery_routes(tmp_path, monkeypatch):
    from app.routers import fitness
    monkeypatch.setattr(fitness.themealdb, "search_meals", lambda q: [{"idMeal": "1", "strMeal": "Demo curry", "strMealThumb": "https://example.test/a.jpg", "strCategory": "Chicken", "strArea": "Indian", "strSource": "https://example.test"}])
    with make_client(tmp_path) as client:
        response = client.post("/workouts", json={"workout_type": "Strength", "duration_min": 45, "intensity": "moderate"})
        assert response.status_code == 201, response.text
        assert client.get("/workouts").json()[0]["workout_type"] == "Strength"
        found = client.get("/recipes/discover?q=curry")
        assert found.status_code == 200, found.text
        assert found.json()[0]["title"] == "Demo curry"
        fuel = client.get("/workout-fuel/recommendations?phase=post")
        assert fuel.status_code == 200, fuel.text


def test_missing_usda_key_is_reported_clearly(tmp_path, monkeypatch):
    monkeypatch.delenv("USDA_FDC_API_KEY", raising=False)
    with make_client(tmp_path) as client:
        response = client.get("/nutrition/search-foods?q=spinach")
        assert response.status_code == 503
        assert "USDA_FDC_API_KEY" in response.json()["detail"]


def test_recipe_micronutrients_only_return_source_attributed_facts(tmp_path):
    with make_client(tmp_path) as client:
        recipes = client.get("/recipes").json()
        assert recipes
        recipe_id = recipes[0]["id"]
        # Attach one explicit source-attributed fact to one ingredient in this recipe.
        # The application exposes only stored facts, never invented micronutrient values.
        from app import db
        conn = db.connect(str(tmp_path / "features.db"))
        ingredient = conn.execute("SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id=? LIMIT 1", (recipe_id,)).fetchone()
        assert ingredient
        conn.execute("INSERT OR REPLACE INTO ingredient_nutrients VALUES(?,?,?,?,?,?)",
                     (ingredient["ingredient_id"], "vitamin_c", 12.5, "mg", "USDA FoodData Central", "12345"))
        conn.commit()
        conn.close()
        response = client.get(f"/nutrition/recipes/{recipe_id}/micronutrients")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["data_complete"] is True
        assert result["micronutrients"][0]["sources"][0]["name"]


def test_frontend_is_served(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "MealMate" in response.text
        assert client.get("/static/app.js").status_code == 200
