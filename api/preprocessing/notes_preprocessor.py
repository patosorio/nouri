"""NotesPreprocessor — hard slot extraction from plan notes (RISK-02)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import UUID

_FUZZY_THRESHOLD = 0.85

_DAY_NAMES: dict[str, int] = {
    "monday": 1,
    "mon": 1,
    "tuesday": 2,
    "tue": 2,
    "tues": 2,
    "wednesday": 3,
    "wed": 3,
    "thursday": 4,
    "thu": 4,
    "thur": 4,
    "thurs": 4,
    "friday": 5,
    "fri": 5,
    "saturday": 6,
    "sat": 6,
    "sunday": 7,
    "sun": 7,
}

_SLOT_ALIASES: dict[str, str] = {
    "breakfast": "breakfast",
    "morning": "breakfast",
    "lunch": "lunch",
    "dinner": "dinner",
    "evening": "dinner",
    "supper": "dinner",
    "snack": "snack",
    "juice": "juice",
}


@dataclass(frozen=True, slots=True)
class RecipeTitleRef:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class HardSlotAssignment:
    day: int
    slot_type: str
    recipe_id: UUID
    recipe_name: str


@dataclass(frozen=True, slots=True)
class AmbiguousRecipeMatch:
    query: str
    candidates: tuple[RecipeTitleRef, ...]


@dataclass(frozen=True, slots=True)
class NotesExtractResult:
    hard_slot_assignments: list[HardSlotAssignment]
    soft_notes_context: str
    ambiguous_matches: list[AmbiguousRecipeMatch]


class NotesPreprocessor:
    def extract(
        self,
        notes: str,
        recipes: list[RecipeTitleRef] | tuple[RecipeTitleRef, ...] = (),
        *,
        duration_days: int = 7,
    ) -> NotesExtractResult:
        text = (notes or "").strip()
        if not text:
            return NotesExtractResult([], "", [])

        library = tuple(recipes)
        assignments: list[HardSlotAssignment] = []
        ambiguous: list[AmbiguousRecipeMatch] = []
        consumed_spans: list[tuple[int, int]] = []

        for recipe in library:
            for match in re.finditer(re.escape(recipe.name), text, flags=re.IGNORECASE):
                span = match.span()
                if self._overlaps(span, consumed_spans):
                    continue
                window_start = max(0, span[0] - 48)
                window_end = min(len(text), span[1] + 48)
                window = text[window_start:window_end]
                days, slot = self._parse_temporal(window, duration_days)
                if not days or slot is None:
                    continue
                for day in days:
                    assignments.append(
                        HardSlotAssignment(
                            day=day,
                            slot_type=slot,
                            recipe_id=recipe.id,
                            recipe_name=recipe.name,
                        )
                    )
                consumed_spans.append(span)

        # Fuzzy pass for titles not already exact-matched
        for recipe in library:
            if any(a.recipe_id == recipe.id for a in assignments):
                continue
            ratio = SequenceMatcher(
                None, recipe.name.lower(), text.lower()
            ).ratio()
            if ratio < _FUZZY_THRESHOLD:
                continue
            near = [
                r
                for r in library
                if SequenceMatcher(None, r.name.lower(), text.lower()).ratio()
                >= _FUZZY_THRESHOLD
            ]
            if len(near) > 1:
                ambiguous.append(
                    AmbiguousRecipeMatch(query=recipe.name, candidates=tuple(near))
                )
                continue
            days, slot = self._parse_temporal(text, duration_days)
            if not days or slot is None:
                continue
            for day in days:
                assignments.append(
                    HardSlotAssignment(
                        day=day,
                        slot_type=slot,
                        recipe_id=recipe.id,
                        recipe_name=recipe.name,
                    )
                )

        soft = text
        for start, end in sorted(consumed_spans, reverse=True):
            soft = soft[:start] + soft[end:]
        soft = re.sub(r"\s{2,}", " ", soft).strip(" ,.;:-")

        return NotesExtractResult(
            hard_slot_assignments=assignments,
            soft_notes_context=soft,
            ambiguous_matches=ambiguous,
        )

    @staticmethod
    def _overlaps(
        span: tuple[int, int], existing: list[tuple[int, int]]
    ) -> bool:
        a, b = span
        for c, d in existing:
            if a < d and b > c:
                return True
        return False

    def _parse_temporal(
        self, window: str, duration_days: int
    ) -> tuple[list[int], str | None]:
        lower = window.lower()
        slot = self._find_slot(lower)

        if re.search(r"\bevery\s+(morning|breakfast)\b", lower):
            return list(range(1, duration_days + 1)), slot or "breakfast"
        if re.search(r"\bevery\s+(lunch|dinner|evening)\b", lower):
            inferred = "lunch" if "lunch" in lower else "dinner"
            return list(range(1, duration_days + 1)), slot or inferred
        if re.search(r"\bevery\s+day\b", lower):
            return list(range(1, duration_days + 1)), slot

        day_match = re.search(r"\bday\s*(\d+)\b", lower)
        if day_match:
            day_n = int(day_match.group(1))
            if 1 <= day_n <= duration_days:
                return [day_n], slot

        for name, day_n in _DAY_NAMES.items():
            if re.search(rf"\b{name}\b", lower):
                if day_n <= duration_days:
                    return [day_n], slot

        if slot is not None:
            return [1], slot
        return [], None

    @staticmethod
    def _find_slot(lower: str) -> str | None:
        for alias, slot in _SLOT_ALIASES.items():
            if re.search(rf"\b{alias}\b", lower):
                return slot
        return None
