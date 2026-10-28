"""Recipe search that understands dishes, ingredients, cuisines, meal types and nutrition goals.

The old search was ``q in title``: "eggs" or "paneer" found nothing, and "high protein breakfast" matched
no titles at all. Here the free text is parsed into
  * constraints  (meal type, diet, max minutes, max calories, min protein)  - applied as hard filters
  * search terms (dish words, ingredient names, cuisine)                    - ALL must match something
and every result gets a relevance score. Nothing unrelated is returned just because it exists: if a recipe
does not match every term it is excluded (it may still appear in a separate, clearly labelled "related" list).
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import MEAL_TYPES, Recipe
from .names import singular

STOPWORDS = {
    "a", "an", "the", "and", "or", "with", "without", "for", "of", "to", "in", "on", "me", "my", "i", "want",
    "recipe", "recipes", "meal", "meals", "dish", "dishes", "food", "foods", "idea", "ideas", "containing",
    "contain", "contains", "using", "use", "that", "have", "has", "least", "most", "than", "under", "over",
    "below", "above", "about", "around", "make", "cook", "some", "good", "best", "easy", "gram", "grams", "g",
    "protein", "calorie", "calories", "kcal", "minute", "minutes", "min", "mins", "high", "low", "quick",
    "fast", "healthy", "gain", "loss", "muscle", "fat", "weight", "lose", "build", "building",
    "vegetarian", "vegan", "gluten", "free", "breakfast", "lunch", "dinner", "snack", "snacks",
}
QUICK_MINUTES, LOW_KCAL, HIGH_PROTEIN, GOAL_PROTEIN = 20, 450, 25, 25
_NUM = r"(\d+(?:\.\d+)?)"


@dataclass
class ParsedQuery:
    raw: str
    terms: list[str] = field(default_factory=list)
    meal_type: str | None = None
    diet: str | None = None
    max_minutes: int | None = None
    max_kcal: float | None = None
    min_protein: float | None = None
    notes: list[str] = field(default_factory=list)  # human-readable "how I read your search"

    def has_nutrition_filter(self) -> bool:
        return self.max_kcal is not None or self.min_protein is not None


def parse_query(text: str, *, meal_type=None, diet=None, max_minutes=None, max_kcal=None, min_protein=None) -> ParsedQuery:
    q = ParsedQuery(raw=text or "", meal_type=meal_type, diet=diet, max_minutes=max_minutes,
                    max_kcal=max_kcal, min_protein=min_protein)
    s = " " + re.sub(r"[-_,;:!?()]+", " ", (text or "").lower()) + " "

    def take(pattern: str) -> re.Match | None:
        nonlocal s
        m = re.search(pattern, s)
        if m:
            s = s[: m.start()] + " " + s[m.end():]
        return m

    if (m := take(rf"\b(?:at least|min(?:imum)?|over|more than|above|with|contain(?:ing|s)?|>=?)?\s*{_NUM}\s*(?:g|grams?)\s*(?:of\s+)?protein\b")) \
            or (m := take(rf"\bprotein\s*(?:of|>=?|over|above)?\s*{_NUM}\s*(?:g|grams?)\b")):
        q.min_protein = q.min_protein if q.min_protein is not None else float(m.group(1))
        q.notes.append(f"at least {m.group(1)} g protein per serving")
    if m := take(rf"\b(?:under|below|less than|max(?:imum)?|within|up to|<=?)\s*{_NUM}\s*(?:kcal|cal(?:ories)?)\b") \
            or take(rf"\b{_NUM}\s*(?:kcal|calories)\s*(?:or less|max)?\b"):
        q.max_kcal = q.max_kcal if q.max_kcal is not None else float(m.group(1))
        q.notes.append(f"at most {m.group(1)} kcal per serving")
    if m := take(rf"\b(?:under|below|less than|within|in|max(?:imum)?|up to|<=?)\s*{_NUM}\s*(?:minutes?|mins?|min)\b") \
            or take(rf"\b{_NUM}\s*(?:minutes?|mins?)\b"):
        q.max_minutes = q.max_minutes if q.max_minutes is not None else int(float(m.group(1)))
        q.notes.append(f"ready in {m.group(1)} minutes or less")
    if take(r"\b(?:quick|fast)\b") and q.max_minutes is None:
        q.max_minutes = QUICK_MINUTES
        q.notes.append(f"quick (≤ {QUICK_MINUTES} min)")
    if take(r"\bhigh\s+protein\b") and q.min_protein is None:
        q.min_protein = HIGH_PROTEIN
        q.notes.append(f"high protein (≥ {HIGH_PROTEIN} g per serving)")
    if take(r"\bmuscle\s+(?:gain|building|build)\b|\bbuild(?:ing)?\s+muscle\b") and q.min_protein is None:
        q.min_protein = GOAL_PROTEIN
        q.notes.append(f"muscle gain: protein-rich (≥ {GOAL_PROTEIN} g per serving)")
    if take(r"\b(?:low\s+calorie|fat\s+loss|weight\s+loss|lose\s+weight)\b") and q.max_kcal is None:
        q.max_kcal = LOW_KCAL
        q.notes.append(f"lighter meals (≤ {LOW_KCAL} kcal per serving)")
    if q.diet is None:
        if take(r"\bvegan\b"):
            q.diet = "vegan"
        elif take(r"\bvegetarian\b|\bveggie\b"):
            q.diet = "vegetarian"
        elif take(r"\bgluten\s+free\b"):
            q.diet = "gluten_free"
    if q.meal_type is None:
        for mt in MEAL_TYPES:
            if take(rf"\b{mt}s?\b"):
                q.meal_type = mt
                break
    q.terms = [t for t in re.findall(r"[a-z][a-z']+", s) if t not in STOPWORDS and len(t) >= 2]
    return q


def _word_hit(term: str, word: str) -> bool:
    if singular(term) == singular(word):
        return True
    return len(term) >= 3 and (word.startswith(term) or singular(word).startswith(singular(term)))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", (text or "").lower())


def _term_score(term: str, r: Recipe) -> float:
    best = 0.0
    if any(_word_hit(term, w) for w in _words(r.title)):
        best = 10.0
    for item in r.ingredients:
        if any(_word_hit(term, w) for w in _words(item.ingredient.name)):
            weight = 2.0 if (item.optional or item.ingredient.is_staple) else 6.0
            best = max(best, weight)
    if r.cuisine and _word_hit(term, r.cuisine):
        best = max(best, 4.0)
    if any(_word_hit(term, t.replace("_", " ")) for t in r.diet_tags):
        best = max(best, 3.0)
    if best == 0.0 and any(_word_hit(term, w) for w in _words(r.description)):
        best = 2.0
    return best


def passes_filters(r: Recipe, q: ParsedQuery) -> bool:
    if q.meal_type and q.meal_type not in r.meal_types:
        return False
    if q.diet and q.diet not in r.diet_tags:
        return False
    if q.max_minutes is not None and r.total_min > q.max_minutes:
        return False
    n = r.nutrition_per_serving
    if q.max_kcal is not None and (not r.nutrition_complete or n.kcal > q.max_kcal):
        return False
    return not (q.min_protein is not None and (not r.nutrition_complete or n.protein < q.min_protein))


def relevance(r: Recipe, q: ParsedQuery, *, require_all: bool = True) -> float | None:
    """None = does not match. Higher = better."""
    if not q.terms:
        return 1.0
    scores = [_term_score(t, r) for t in q.terms]
    if require_all and any(s == 0 for s in scores):
        return None
    if not require_all and all(s == 0 for s in scores):
        return None
    total = sum(scores)
    phrase = " ".join(q.terms)
    if len(q.terms) > 1 and phrase in r.title.lower():
        total += 15
    return total


@dataclass
class SearchOutcome:
    query: ParsedQuery
    hits: list[tuple[Recipe, float]]
    related: list[tuple[Recipe, float]]
    suggestions: list[str]


def search(recipes: Iterable[Recipe], text: str, **filters) -> SearchOutcome:
    recipes = list(recipes)
    q = parse_query(text, **filters)
    hits = []
    for r in recipes:
        if passes_filters(r, q) and (s := relevance(r, q)) is not None:
            hits.append((r, s))
    hits.sort(key=lambda t: (-t[1], t[0].title))
    related: list[tuple[Recipe, float]] = []
    suggestions: list[str] = []
    if not hits:
        if len(q.terms) > 1:  # partial matches, clearly labelled as such by the caller
            seen = set()
            for r in recipes:
                if passes_filters(r, q) and (s := relevance(r, q, require_all=False)) is not None and r.id not in seen:
                    seen.add(r.id)
                    related.append((r, s))
            related.sort(key=lambda t: (-t[1], t[0].title))
        if q.has_nutrition_filter() or q.max_minutes is not None:
            relaxed = ParsedQuery(raw=q.raw, terms=q.terms, meal_type=q.meal_type, diet=q.diet)
            n = sum(1 for r in recipes if passes_filters(r, relaxed) and relevance(r, relaxed) is not None)
            if n:
                suggestions.append(f"Remove the nutrition/time limits: {n} recipe{'s' if n != 1 else ''} match the rest of your search.")
        if q.terms:
            suggestions.append("Search TheMealDB for more dishes, or try a single ingredient such as '" + q.terms[0] + "'.")
        else:
            suggestions.append("Try loosening the filters, or search by dish or ingredient.")
    return SearchOutcome(q, hits, related[:12], suggestions)


def sort_key(sort: str, q: ParsedQuery, relevance_score: float, recipe: Recipe, coverage: float, pantry_score: float):
    """Sort key for a result row (ascending). ``sort`` is relevance | time | calories | protein | pantry."""
    n = recipe.nutrition_per_serving
    if sort == "time":
        return (recipe.total_min, recipe.title)
    if sort == "calories":
        return (n.kcal, recipe.title)
    if sort == "protein":
        return (-n.protein, recipe.title)
    if sort == "pantry":
        return (-coverage, -pantry_score, recipe.title)
    # relevance: text match first; for pure nutrition searches rank by the thing asked for
    if q.terms:
        return (-relevance_score, -coverage, recipe.title)
    if q.min_protein is not None:
        return (-n.protein, recipe.title)
    if q.max_kcal is not None:
        return (n.kcal, recipe.title)
    return (-coverage, -pantry_score, recipe.title)
