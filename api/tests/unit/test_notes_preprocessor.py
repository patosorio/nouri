"""NotesPreprocessor unit tests — docs/8_TEST_PLAN.md §3.2 / RISK-02."""

from __future__ import annotations

from uuid import uuid4

import pytest

from preprocessing.notes_preprocessor import NotesPreprocessor, RecipeTitleRef

# RISK-02 covered by: test_extract_slot_assignment_every_morning,
# test_extract_recipe_name_reference_resolves_to_id


@pytest.fixture
def preprocessor() -> NotesPreprocessor:
    return NotesPreprocessor()


@pytest.fixture
def library() -> list[RecipeTitleRef]:
    return [
        RecipeTitleRef(id=uuid4(), name="Sunrise Green Juice"),
        RecipeTitleRef(id=uuid4(), name="Golden Turmeric Overnight Oats"),
    ]


def test_extract_recipe_name_reference_resolves_to_id(
    preprocessor: NotesPreprocessor, library: list[RecipeTitleRef]
) -> None:
    # RISK-02 covered by: test_extract_recipe_name_reference_resolves_to_id
    notes = "For Monday dinner please use Sunrise Green Juice from my recipes"
    result = preprocessor.extract(notes, library, duration_days=7)
    assert len(result.hard_slot_assignments) >= 1
    assert result.hard_slot_assignments[0].recipe_id == library[0].id


def test_extract_slot_assignment_every_morning(
    preprocessor: NotesPreprocessor, library: list[RecipeTitleRef]
) -> None:
    # RISK-02 covered by: test_extract_slot_assignment_every_morning
    notes = "every morning I want Golden Turmeric Overnight Oats"
    result = preprocessor.extract(notes, library, duration_days=7)
    breakfasts = [
        a for a in result.hard_slot_assignments if a.slot_type == "breakfast"
    ]
    assert len(breakfasts) == 7


def test_extract_slot_assignment_specific_day(
    preprocessor: NotesPreprocessor, library: list[RecipeTitleRef]
) -> None:
    notes = "Monday dinner: Sunrise Green Juice"
    result = preprocessor.extract(notes, library, duration_days=7)
    assert any(
        a.day == 1 and a.slot_type == "dinner" for a in result.hard_slot_assignments
    )


def test_unrecognised_recipe_name_not_added_to_assignments(
    preprocessor: NotesPreprocessor, library: list[RecipeTitleRef]
) -> None:
    notes = "every morning I want Mystery Unicorn Smoothie"
    result = preprocessor.extract(notes, library, duration_days=7)
    assert result.hard_slot_assignments == []


def test_remaining_notes_text_preserved_after_extraction(
    preprocessor: NotesPreprocessor, library: list[RecipeTitleRef]
) -> None:
    notes = (
        "Please use Sunrise Green Juice for Monday breakfast. "
        "I also prefer meals under 20 minutes."
    )
    result = preprocessor.extract(notes, library, duration_days=7)
    assert "under 20 minutes" in result.soft_notes_context.lower() or (
        "prefer" in result.soft_notes_context.lower()
    )
