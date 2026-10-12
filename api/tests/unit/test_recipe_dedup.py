"""Save-time recipe reuse matching."""

from services.recipe_dedup import (
    exact_name_match,
    should_reuse_existing,
)


def test_exact_name_reuses() -> None:
    assert should_reuse_existing(
        draft_name="Cashew Alfredo",
        draft_ingredients={"cashews", "garlic"},
        existing_name="cashew alfredo",
        existing_ingredients={"cashews", "lemon"},
    )


def test_fuzzy_name_reuses_when_ingredients_overlap() -> None:
    assert should_reuse_existing(
        draft_name="Creamy Cashew Alfredo Pasta",
        draft_ingredients={"cashews", "garlic", "pasta", "lemon"},
        existing_name="Cashew Alfredo Pasta",
        existing_ingredients={"cashews", "garlic", "pasta"},
    )


def test_fuzzy_name_inserts_when_ingredients_differ() -> None:
    assert not should_reuse_existing(
        draft_name="Cashew Alfredo Pasta",
        draft_ingredients={"cashews", "nutritional yeast", "pasta"},
        existing_name="Cashew Alfredo Cake",
        existing_ingredients={"cashews", "dates", "cocoa"},
    )


def test_same_content_key_reuses_even_if_titles_diverge() -> None:
    assert should_reuse_existing(
        draft_name="Kale Citrus Salad",
        draft_ingredients={"kale", "orange", "olive oil"},
        existing_name="Kale Citrus Salad",
        existing_ingredients={"orange", "kale", "olive oil"},
    )


def test_unrelated_names_do_not_match() -> None:
    assert not exact_name_match("Kale Salad", "Cashew Alfredo")
    assert not should_reuse_existing(
        draft_name="Kale Salad",
        draft_ingredients={"kale"},
        existing_name="Cashew Alfredo",
        existing_ingredients={"cashews"},
    )
