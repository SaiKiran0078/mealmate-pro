from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _auth(client: TestClient) -> dict[str, str]:
    client.post("/auth/register", json={"email": "cook@example.com", "password": "password123"})
    token = client.post("/auth/login", json={"email": "cook@example.com", "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_recipe_favourites_and_ratings_are_saved_per_user(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "feedback.db"), jwt_secret="t" * 32))
    with TestClient(app) as client:
        auth = _auth(client)
        recipes = client.get("/recipes", headers=auth).json()
        recipe_id = recipes[0]["id"]

        saved = client.put(f"/recipes/{recipe_id}/feedback", json={"favorite": True, "rating": 5}, headers=auth)
        assert saved.status_code == 200
        assert saved.json() == {"recipe_id": recipe_id, "favorite": True, "rating": 5}
        favorites = client.get("/recipes/favorites", headers=auth)
        assert favorites.status_code == 200
        assert any(row["id"] == recipe_id and row["rating"] == 5 for row in favorites.json())

        changed = client.put(f"/recipes/{recipe_id}/feedback", json={"favorite": False}, headers=auth)
        assert changed.json()["favorite"] is False
        assert all(row["id"] != recipe_id for row in client.get("/recipes/favorites", headers=auth).json())
        # Updating the favourite flag does not erase a rating.
        assert client.put(f"/recipes/{recipe_id}/feedback", json={"favorite": True}, headers=auth).json()["rating"] == 5


def test_pantry_suggestions_include_partial_matches_and_ready_recipe(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "pantry.db"), jwt_secret="t" * 32))
    with TestClient(app) as client:
        auth = _auth(client)
        for name, amount, unit in [("Eggs", 6, "pcs"), ("Tomatoes", 3, "pcs"), ("Onions", 2, "pcs")]:
            response = client.post("/pantry", json={"ingredient": name, "amount": amount, "unit": unit}, headers=auth)
            assert response.status_code == 201
        suggestions = client.get("/recipes/suggestions?min_coverage=0.15", headers=auth).json()
        assert suggestions
        assert any(item["status"] == "ready" for item in suggestions)
        assert any(item["missing"] for item in suggestions)


def test_new_builtin_recipe_is_added_to_an_existing_database(tmp_path):
    from app import db

    path = tmp_path / "upgrade.db"
    settings = Settings(db_path=str(path), jwt_secret="t" * 32)
    with TestClient(create_app(settings)):
        pass
    conn = db.connect(str(path))
    try:
        conn.execute("DELETE FROM recipes WHERE title = ?", ("Quick Tomato, Onion & Egg Scramble",))
        conn.commit()
        assert conn.execute("SELECT 1 FROM recipes WHERE title = ?", ("Quick Tomato, Onion & Egg Scramble",)).fetchone() is None
    finally:
        conn.close()
    # Startup migration adds the missing catalog recipe without reseeding/replacing the database.
    with TestClient(create_app(settings)) as client:
        auth = _auth(client)
        titles = [recipe["title"] for recipe in client.get("/recipes", headers=auth).json()]
        assert "Quick Tomato, Onion & Egg Scramble" in titles
