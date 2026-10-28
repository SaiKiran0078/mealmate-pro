"""Settings come from environment variables (12-factor style)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    db_path: str = "mealmate.db"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    token_minutes: int = 60 * 24
    seed_on_startup: bool = True


def resolve_db_path(value: str) -> str:
    """Relative database paths are anchored to the project folder, not to whatever directory the server
    happened to be started from. (Starting uvicorn from another folder used to silently create a second,
    empty database - saved plans and pantry "disappeared".)"""
    if value == ":memory:":
        return value
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")  # works from any working directory; real environment variables win
    return Settings(
        db_path=resolve_db_path(os.getenv("MEALMATE_DB", "mealmate.db")),
        jwt_secret=os.getenv("JWT_SECRET", ""),
        token_minutes=int(os.getenv("TOKEN_MINUTES", str(60 * 24))),
        seed_on_startup=os.getenv("SEED_ON_STARTUP", "1") == "1",
    )
