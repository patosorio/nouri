"""Worker mapping — drop unused generate_new drafts; remap reused ids."""

from decimal import Decimal
from uuid import uuid4

from db.models import PlanItemSource, PlanSlot, RecipeType
from schemas.plans import GeneratedPlanData, GeneratedPlanDay, GeneratedPlanItem
from schemas.recipes import RecipeDraft
from worker.agent_to_service import (
    filter_unplaced_generated,
    placed_recipe_ids,
    remap_reused_recipe_ids,
)


def _item(recipe_id, title: str = "Bowl") -> GeneratedPlanItem:
    return GeneratedPlanItem(
        slot_type=PlanSlot.LUNCH,
        recipe_title=title,
        recipe_id=recipe_id,
        recipe_type=RecipeType.MEAL,
        item_source=PlanItemSource.AI_GENERATED,
        calories=Decimal(500),
    )


def test_filter_unplaced_generated_keeps_only_assigned_drafts() -> None:
    placed = uuid4()
    unused = uuid4()
    plan = GeneratedPlanData(
        days=[GeneratedPlanDay(day_number=1, items=[_item(placed)])],
        generated_recipes=[
            RecipeDraft(id=placed, name="Used"),
            RecipeDraft(id=unused, name="Unused"),
        ],
    )
    filtered = filter_unplaced_generated(plan)
    assert placed_recipe_ids(filtered) == {placed}
    assert [d.name for d in filtered.generated_recipes] == ["Used"]


def test_remap_reused_recipe_ids_points_slots_at_existing_row() -> None:
    generated_id = uuid4()
    existing_id = uuid4()
    plan = GeneratedPlanData(
        days=[GeneratedPlanDay(day_number=1, items=[_item(generated_id, "Alfredo")])],
        generated_recipes=[RecipeDraft(id=generated_id, name="Alfredo")],
    )
    remapped = remap_reused_recipe_ids(plan, {generated_id: existing_id})
    item = remapped.days[0].items[0]
    assert item.recipe_id == existing_id
    assert item.item_source == PlanItemSource.SAVED_RECIPE
    assert remapped.generated_recipes == []
