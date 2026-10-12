"""Token containment for exclusion names.

``contains(ingredient, exclusion)`` is true when the exclusion's tokens appear
as a contiguous run inside the ingredient's tokens, after light singularizing.

This is deliberately conservative: ``milk`` matches ``coconut milk`` because
the token ``milk`` is present. A narrower food-ontology match is out of scope.
``nut`` matches ``mixed nuts`` and does not match ``peanut`` — matching is by
token, not by substring. ``egg`` does not match ``eggplant``. ``pine nut``
does not match ``pineapple``.
"""

from __future__ import annotations

import re

from services._helpers import normalise_ingredient_name

_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(value: str) -> list[str]:
    raw = _TOKEN.findall(normalise_ingredient_name(value))
    return [singularize(token) for token in raw]


def singularize(word: str) -> str:
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def contains(ingredient: str, exclusion: str) -> bool:
    """True when every exclusion token sits in a row inside the ingredient."""
    ingredient_tokens = tokens(ingredient)
    exclusion_tokens = tokens(exclusion)
    if not exclusion_tokens or not ingredient_tokens:
        return False
    width = len(exclusion_tokens)
    if width > len(ingredient_tokens):
        return False
    for start in range(len(ingredient_tokens) - width + 1):
        if ingredient_tokens[start : start + width] == exclusion_tokens:
            return True
    return False
