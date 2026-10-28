"""Ingredient-name resolution: turn what a person types into a known ingredient.

Why this exists: the old lookup only stripped a trailing "s", so "tomatoes" became
"tomatoe" and "chicken" never matched "chicken breast". The pantry then held a
brand-new, nutrition-less ingredient that no recipe used, so recommendations were
empty. Resolution is deliberately conservative: plural/spelling variants and an
explicit alias table only. Different ingredients ("coconut milk" vs "milk") are
never merged just because the words overlap.
"""
from __future__ import annotations

import re

# Words that do not change what the ingredient is.
FILLER = {"fresh", "raw", "large", "small", "medium", "ripe", "organic", "chopped", "diced", "sliced",
          "minced", "boneless", "skinless", "whole"}

# Typed name (already singular + lowercase) -> catalog name. Only unambiguous generic -> specific pairs.
ALIASES = {
    "chicken": "chicken breast", "chicken meat": "chicken breast",
    "cheese": "cheddar cheese", "cheddar": "cheddar cheese",
    "lentil": "red lentils", "red lentil": "red lentils", "masoor dal": "red lentils", "dal": "red lentils",
    "tin tomato": "canned tomatoes", "tinned tomato": "canned tomatoes", "canned tomato": "canned tomatoes",
    "tomato can": "canned tomatoes", "chopped tomato": "canned tomatoes",
    "tuna": "canned tuna", "tinned tuna": "canned tuna",
    "capsicum": "bell pepper", "sweet pepper": "bell pepper",
    "garlic clove": "garlic", "clove garlic": "garlic",
    "curd": "yogurt", "dahi": "yogurt", "yoghurt": "yogurt", "plain yogurt": "yogurt",
    "chana": "chickpeas", "garbanzo": "chickpeas", "garbanzo bean": "chickpeas", "chickpea": "chickpeas",
    "chilli powder": "chili powder", "red chilli powder": "chili powder", "red chili powder": "chili powder",
    "oil": "olive oil", "cooking oil": "olive oil",
    "soya sauce": "soy sauce", "soy": "soy sauce",
    "rolled oat": "oats", "oat": "oats", "oatmeal": "oats",
    "cottage cheese": "paneer",
    "wrap": "tortilla", "chapati": "tortilla",
    "spaghetti": "pasta", "penne": "pasta", "macaroni": "pasta",
    "basmati rice": "rice", "white rice": "rice",
    "peanut butter": "peanut butter",
}

_KEEP_S = ("ss", "us", "is")  # hummus, couscous, asparagus, molasses-like words


def singular(word: str) -> str:
    w = word.lower()
    if len(w) <= 3 or w.endswith(_KEEP_S):
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"          # berries -> berry
    if w.endswith(("oes", "ches", "shes", "xes")):
        return w[:-2]                # tomatoes -> tomato, peaches -> peach
    if w.endswith("ves"):
        return w[:-3] + "f"          # halves -> half (loaves -> loaf)
    if w.endswith("s"):
        return w[:-1]                # eggs -> egg
    return w


def normalize(raw: str) -> str:
    """'  Fresh Tomatoes (ripe) ' -> 'tomato'."""
    text = re.sub(r"\(.*?\)", " ", raw or "").lower()
    words = re.findall(r"[a-z][a-z'-]*", text)
    words = [w for w in words if w not in FILLER]
    return " ".join(singular(w) if i == len(words) - 1 else w for i, w in enumerate(words)).strip()


def candidates(raw: str) -> list[str]:
    """Names to try, best first (all lowercase, deduplicated)."""
    base = normalize(raw)
    seen: list[str] = []

    def add(x: str | None) -> None:
        if x and x not in seen:
            seen.append(x)

    add(re.sub(r"\s+", " ", (raw or "").strip().lower()))
    add(base)
    add(ALIASES.get(base))
    # every word singular ("red lentils" typed as "red lentil")
    add(" ".join(singular(w) for w in base.split()))
    if base.endswith("s"):
        add(base[:-1])
    return seen


def resolve(raw: str, known: dict[str, object]):
    """Return the entry of ``known`` (keyed by lowercase name) matching ``raw``, or None."""
    for name in candidates(raw):
        if name in known:
            return known[name]
    # catalog names may themselves be plural ("oats"): compare normalized forms too
    normalized = {normalize(k): v for k, v in known.items()}
    for name in candidates(raw):
        if name in normalized:
            return normalized[name]
        alias = ALIASES.get(name)
        if alias and alias in known:
            return known[alias]
    return None


def similar(raw: str, known_names: list[str], limit: int = 4) -> list[str]:
    """Names sharing a word with ``raw``: shown as 'did you mean' hints, never auto-merged."""
    words = {singular(w) for w in normalize(raw).split()}
    if not words:
        return []
    hits = [n for n in known_names if words & {singular(w) for w in n.split()}]
    return sorted(hits)[:limit]
