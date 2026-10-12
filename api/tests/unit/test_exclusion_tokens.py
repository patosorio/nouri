"""Token containment for exclusions. milk matches coconut milk on purpose."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from agent.plan_generator import PlanGeneratorAgent
from schemas.agent import GeneratedPlanData, GeneratedPlanDayAI, GeneratedPlanItemAI
from validation.exclusion_checker import ExclusionChecker
from validation.plan_validator import PlanValidator
from validation.text_match import contains
from validation.types import (
    ExclusionView,
    MacroTargets,
    PlanDayView,
    PlanDraftView,
    PlanItemView,
    RecipeIngredientView,
    RecipeView,
    UserProfileView,
)


@pytest.mark.parametrize(
    ("ingredient", "exclusion", "expected"),
    [
        ("peanut butter", "peanut", True),
        ("peanuts", "peanut", True),
        ("mixed nuts", "nut", True),
        ("peanut", "nut", False),
        ("eggplant", "egg", False),
        ("pineapple", "pine nut", False),
        ("coconut milk", "milk", True),
    ],
)
def test_contains_token_table(ingredient: str, exclusion: str, expected: bool) -> None:
    assert contains(ingredient, exclusion) is expected


def test_saved_snapshot_ingredients_are_exclusion_checked() -> None:
    recipe_id = uuid4()
    plan = GeneratedPlanData(
        days=[
            GeneratedPlanDayAI(
                day_number=1,
                items=[
                    GeneratedPlanItemAI(
                        slot_type="lunch",
                        recipe_id=recipe_id,
                        recipe_title="Satay",
                    )
                ],
            )
        ]
    )
    draft = PlanGeneratorAgent()._to_plan_draft_view(
        plan,
        {
            recipe_id: SimpleNamespace(
                ingredients=[
                    SimpleNamespace(name="peanut butter", ingredient_id=uuid4())
                ]
            )
        },
        {},
    )
    result = PlanValidator().validate(
        draft,
        UserProfileView(
            cooking_type="cooked_100",
            exclusions=(ExclusionView(raw_name="peanut", ingredient_id=uuid4()),),
        ),
        MacroTargets(calories=0, protein_g=0, carbs_g=0, fat_g=0, fiber_g=0),
    )
    assert result.passed is False
    assert any("satay" in error.lower() for error in result.errors)


def test_saved_item_without_loaded_ingredients_fails_closed() -> None:
    plan = GeneratedPlanData(
        days=[
            GeneratedPlanDayAI(
                day_number=1,
                items=[
                    GeneratedPlanItemAI(
                        slot_type="lunch",
                        recipe_id=uuid4(),
                        recipe_title="Mystery",
                    )
                ],
            )
        ]
    )
    with pytest.raises(Exception, match="not loaded"):
        PlanGeneratorAgent()._to_plan_draft_view(plan, {}, {})


def test_saved_peanut_butter_fails_when_peanut_is_excluded() -> None:
    recipe_id = uuid4()
    draft = PlanDraftView(
        days=(
            PlanDayView(
                day_number=1,
                items=(
                    PlanItemView(
                        day_number=1,
                        name="Satay",
                        recipe_id=recipe_id,
                        ingredients=(
                            RecipeIngredientView(
                                name="peanut butter", ingredient_id=uuid4()
                            ),
                        ),
                    ),
                ),
            ),
        )
    )
    result = PlanValidator().validate(
        draft,
        UserProfileView(
            cooking_type="cooked_100",
            exclusions=(
                ExclusionView(raw_name="peanut", ingredient_id=uuid4()),
            ),
        ),
        MacroTargets(calories=0, protein_g=0, carbs_g=0, fat_g=0, fiber_g=0),
    )
    assert result.passed is False
    assert any("excluded ingredient" in error.lower() for error in result.errors)
    assert (
        ExclusionChecker().check_recipe(
            RecipeView(
                id=recipe_id,
                ingredients=draft.days[0].items[0].ingredients,
            ),
            (ExclusionView(raw_name="peanut", ingredient_id=uuid4()),),
        )
        is False
    )
