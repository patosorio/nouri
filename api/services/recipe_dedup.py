"""Match generate_new drafts against the user's existing recipes before INSERT."""

from __future__ import annotations

from difflib import SequenceMatcher

_FUZZY_NAME = 0.85
_MIN_INGREDIENT_JACCARD = 0.5


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def exact_name_match(left: str, right: str) -> bool:
    a = normalize_name(left)
    b = normalize_name(right)
    return bool(a) and a == b


def fuzzy_name_ratio(left: str, right: str) -> float:
    a = normalize_name(left)
    b = normalize_name(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def ingredient_jaccard(left: set[str], right: set[str]) -> float:
    a = {normalize_name(n) for n in left if normalize_name(n)}
    b = {normalize_name(n) for n in right if normalize_name(n)}
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def content_key(name: str, ingredient_names: list[str] | tuple[str, ...]) -> str:
    names = ",".join(
        sorted(normalize_name(n) for n in ingredient_names if normalize_name(n))
    )
    return f"{normalize_name(name)}|{names}"


def should_reuse_existing(
    *,
    draft_name: str,
    draft_ingredients: set[str],
    existing_name: str,
    existing_ingredients: set[str],
) -> bool:
    draft_key = content_key(draft_name, tuple(draft_ingredients))
    existing_key = content_key(existing_name, tuple(existing_ingredients))
    if draft_key == existing_key:
        return True
    if exact_name_match(draft_name, existing_name):
        return True
    if fuzzy_name_ratio(draft_name, existing_name) < _FUZZY_NAME:
        return False
    return (
        ingredient_jaccard(draft_ingredients, existing_ingredients)
        >= _MIN_INGREDIENT_JACCARD
    )
