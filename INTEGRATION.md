# MealMate Pro Frontend Integration

This package adds a responsive HTML/CSS/JavaScript frontend served by the existing FastAPI application. It does not replace backend routers or database logic.

## Files

- `app/static/index.html` — application UI
- `app/static/styles.css` — responsive visual design
- `app/static/app.js` — API integration and page interactions

## Integrate into `app/main.py`

Add these imports near the top of `app/main.py`:

```python
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
```

Inside `create_app`, immediately after `app = FastAPI(...)` and `app.state.settings = settings`, add:

```python
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(static_dir / "index.html")
```

Keep your existing exception handler, health route, and router registrations unchanged. Do not add a second `create_app` function or remove any existing routes.

## Run locally in PowerShell

From `C:\Users\sajja\Downloads\mealmate`:

```powershell
.\.venv312\Scripts\Activate.ps1
$env:JWT_SECRET = "your-existing-random-secret-of-at-least-16-characters"
python -m uvicorn app.main:create_app --factory --reload
```

If you do not have a secret set in the current terminal, generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set the generated value with `$env:JWT_SECRET = "paste-generated-value"` before starting Uvicorn. Do not commit real secrets to GitHub.

Open `http://127.0.0.1:8000/`. API documentation remains available at `http://127.0.0.1:8000/docs`.

## Important notes

- This frontend expects the current API routes: `/auth/register`, `/auth/login`, `/me`, `/pantry`, `/recipes`, `/recipes/suggestions`, `/recipes/{id}`, `/recipes/{id}/guide`, `/plans`, and `/plans/generate`.
- The frontend uses `localStorage` for the bearer token. This is convenient for a local portfolio project, but production apps should evaluate secure cookie-based authentication and other security controls.
- If your API response serializers use different property names for pantry or meal-plan objects, small mapping adjustments may be needed. The UI includes fallback handling for common response shapes.
- The recipe illustration uses emoji as lightweight placeholders rather than external food photos.
