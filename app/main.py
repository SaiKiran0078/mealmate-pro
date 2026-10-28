"""Application factory. Run with:  uvicorn app.main:create_app --factory"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from . import db
from .config import Settings, load_settings
from .core.units import UnitError
from .routers import auth, dashboard, fitness, pantry, plans, recipes
from .repositories import ingredients as ingredient_repo
from .seed.seeder import seed_if_empty, seed_missing_recipes

log = logging.getLogger("uvicorn.error")

DESCRIPTION = """
**MealMate Pro** turns the food you already have into a meal plan.

1. Register and log in, then click **Authorize** and paste your token.
2. Add what is in your kitchen with `POST /pantry`.
3. See what you can cook right now with `GET /recipes/suggestions`.
4. Generate a daily or weekly plan with `POST /plans/generate`.
5. Open `GET /recipes/{id}/guide` for step-by-step cooking help.
6. Use the **Fitness & nutrition** page to set estimated targets, log consumed food and workouts, compare planned versus actual intake, and discover external recipes.
7. Configure `USDA_FDC_API_KEY` to import source-attributed vitamin/mineral facts from USDA FoodData Central.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    conn = db.connect(settings.db_path)
    db.init_db(conn)
    if settings.seed_on_startup:
        seed_if_empty(conn)
        added_recipes = seed_missing_recipes(conn)
        if added_recipes:
            log.info("Added %d new built-in recipe(s).", added_recipes)
    merged = ingredient_repo.repair_duplicates(conn)  # fixes look-alike ingredients created by older versions
    if merged:
        log.info("Merged %d duplicate ingredient(s) into their catalog entries.", merged)
    log.info("MealMate database: %s", Path(settings.db_path).resolve() if settings.db_path != ":memory:" else ":memory:")
    conn.close()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    if len(settings.jwt_secret) < 16:
        raise RuntimeError("JWT_SECRET must be set to a random string of at least 16 characters.")

    app = FastAPI(title="MealMate Pro", version="1.3.0", description=DESCRIPTION, lifespan=lifespan)
    app.state.settings = settings
    static_dir = Path(__file__).parent / "static"

    app.mount(
        "/static",
        StaticFiles(directory=static_dir),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    def homepage():
        return FileResponse(static_dir / "index.html")

    @app.exception_handler(UnitError)
    async def unit_error_handler(_: Request, exc: UnitError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok"}

    for module in (auth, pantry, dashboard, fitness, recipes, plans):
        app.include_router(module.router)
    return app
