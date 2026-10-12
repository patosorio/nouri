"""Plan list/detail attach job progress for the Creating card (URS FR-3.3)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from db.models import JobStatus, JuiceTime, PlanItemSource, PlanSlot, RecipeType
from routers.serializers import (
    serialize_generation,
    serialize_plan_day,
    serialize_plan_item,
)


def test_serialize_generation_none() -> None:
    assert serialize_generation(None) is None


def test_serialize_generation_running_progress() -> None:
    job = SimpleNamespace(
        id=uuid4(),
        status=JobStatus.RUNNING,
        result={
            "progress_pct": 25,
            "stage": "generating_week",
            "days_completed": 0,
            "days_total": 7,
        },
        error_message=None,
        attempts=1,
    )
    data = serialize_generation(job)
    assert data is not None
    assert data["status"] == "running"
    assert data["progress_pct"] == 25
    assert data["stage"] == "generating_week"
    assert data["days_completed"] == 0
    assert data["days_total"] == 7


def test_serialize_generation_completed_is_100() -> None:
    job = SimpleNamespace(
        id=uuid4(),
        status=JobStatus.COMPLETED,
        result={
            "progress_pct": 95,
            "stage": "writing_days",
            "days_completed": 7,
            "days_total": 7,
        },
        error_message=None,
        attempts=1,
    )
    data = serialize_generation(job)
    assert data is not None
    assert data["status"] == "completed"
    assert data["progress_pct"] == 100


def test_serialize_plan_item_returns_juice_fields() -> None:
    plan_id = uuid4()
    item = SimpleNamespace(
        id=uuid4(),
        slot=PlanSlot.JUICE,
        recipe_id=uuid4(),
        name="Green juice",
        description=None,
        recipe_type=RecipeType.JUICE,
        item_source=PlanItemSource.SAVED_RECIPE,
        prep_method=None,
        color=None,
        prep_minutes=None,
        slot_order=0,
        juice_time=JuiceTime.MORNING,
        juice_size_ml=500,
        nutrition_unknown=False,
        calories=120,
        protein_g=2,
        carbs_g=28,
        fat_g=0,
        fiber_g=1,
    )
    data = serialize_plan_item(item, day_number=1, plan_id=plan_id)
    assert data["juice_time"] == "morning"
    assert data["juice_size_ml"] == 500
    assert data["nutrition_unknown"] is False


def test_serialize_plan_day_returns_totals_incomplete() -> None:
    plan_id = uuid4()
    day = SimpleNamespace(
        id=uuid4(),
        day_number=1,
        date=date(2026, 10, 11),
        calories_actual=None,
        protein_g_actual=None,
        carbs_g_actual=None,
        fat_g_actual=None,
        fiber_g_actual=None,
        calories_target=2000,
        protein_g_target=80,
        carbs_g_target=250,
        fat_g_target=70,
        fiber_g_target=30,
        totals_incomplete=True,
    )
    data = serialize_plan_day(day, [], plan_id=plan_id)
    assert data["totals_incomplete"] is True
    assert data["items"] == []
