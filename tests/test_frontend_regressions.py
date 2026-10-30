from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_food_diary_numeric_fields_accept_decimal_values():
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    for field_id in ("diary-kcal", "diary-protein", "diary-carbs", "diary-fat"):
        field = html.split(f'id="{field_id}"', maxsplit=1)[1].split(">", maxsplit=1)[0]
        assert 'step="any"' in field


def test_food_diary_resets_after_success_and_refreshes_summary():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'const form = event.currentTarget;' in js
    assert 'form.reset();' in js
    assert 'await refreshFitness();' in js
    assert '$("#diary-meal").value = "";' in js


def test_session_restore_does_not_clear_token_for_transient_errors():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'if (error.status === 401)' in js
    assert 'localStorage.removeItem("mealmate_token");' in js
    assert 'localStorage.setItem("mealmate_last_page", valid);' in js


def test_planned_nutrition_is_the_comparison_target_when_meals_exist_and_no_plan_shows_eaten_only():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert "planned[key]" in js
    assert 'Eaten vs planned nutrition' in js
    assert '"Eaten vs daily target"' not in js
    assert 'Eaten nutrition' in js
    assert 'Logged today' in js
    assert "eaten-only-grid" in js
