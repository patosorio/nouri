"""Plan skeleton: juicing, pins, and stable slot order. No model calls."""

from __future__ import annotations

from uuid import uuid4

import pytest
from planning.skeleton import (
    JuiceSlotConfig,
    Pin,
    SkeletonError,
    build_skeleton,
)


def test_juicing_off_has_no_juice_slots() -> None:
    skeleton = build_skeleton(
        duration_days=2,
        juicing_enabled=False,
        juice_configs=None,
        pins=(),
    )
    assert skeleton.slots
    assert all(slot.kind == "meal" for slot in skeleton.slots)
    assert {slot.slot for slot in skeleton.slots} == {"breakfast", "lunch", "dinner"}


def test_juicing_on_without_config_uses_morning_500_and_pre_lunch_250() -> None:
    skeleton = build_skeleton(
        duration_days=3,
        juicing_enabled=True,
        juice_configs=(),
        pins=(),
    )
    for day_number in (1, 2, 3):
        juices = [slot for slot in skeleton.for_day(day_number) if slot.kind == "juice"]
        assert [(slot.juice_time, slot.juice_size_ml) for slot in juices] == [
            ("morning", 500),
            ("pre_lunch", 250),
        ]


def test_configured_rows_keep_order_and_sizes() -> None:
    skeleton = build_skeleton(
        duration_days=1,
        juicing_enabled=True,
        juice_configs=(
            JuiceSlotConfig(time_of_day="afternoon", size_ml=750, slot_order=2),
            JuiceSlotConfig(time_of_day="morning", size_ml=125, slot_order=0),
        ),
        pins=(),
    )
    juices = [slot for slot in skeleton.for_day(1) if slot.kind == "juice"]
    assert [(slot.juice_time, slot.juice_size_ml, slot.slot_order) for slot in juices] == [
        ("morning", 125, 0),
        ("afternoon", 750, 2),
    ]


def test_smoothie_pin_creates_a_smoothie_slot() -> None:
    recipe_id = uuid4()
    skeleton = build_skeleton(
        duration_days=1,
        juicing_enabled=True,
        juice_configs=(),
        pins=(Pin(1, "smoothie", recipe_id, "smoothie"),),
    )
    smoothies = [slot for slot in skeleton.for_day(1) if slot.kind == "smoothie"]
    assert len(smoothies) == 1
    assert smoothies[0].slot == "smoothie"
    assert smoothies[0].pinned_recipe_id == recipe_id
    assert smoothies[0].to_fill is False


def test_slot_and_recipe_type_must_match() -> None:
    recipe_id = uuid4()
    with pytest.raises(SkeletonError):
        build_skeleton(
            duration_days=1,
            juicing_enabled=True,
            juice_configs=(),
            pins=(Pin(1, "breakfast", recipe_id, "juice"),),
        )
    with pytest.raises(SkeletonError):
        build_skeleton(
            duration_days=1,
            juicing_enabled=True,
            juice_configs=(),
            pins=(Pin(1, "smoothie", recipe_id, "juice"),),
        )
    with pytest.raises(SkeletonError):
        build_skeleton(
            duration_days=1,
            juicing_enabled=False,
            juice_configs=(),
            pins=(Pin(1, "juice", recipe_id, "juice"),),
        )


def test_juice_only_day_is_valid() -> None:
    skeleton = build_skeleton(
        duration_days=1,
        juicing_enabled=True,
        juice_configs=(),
        pins=(),
        meal_slots=(),
    )
    day = skeleton.for_day(1)
    assert day
    assert all(slot.kind == "juice" for slot in day)


def test_skeleton_is_deterministic() -> None:
    pins = (Pin(2, "lunch", uuid4(), "meal"),)
    configs = (JuiceSlotConfig("evening", 250, 1),)
    first = build_skeleton(
        duration_days=2,
        juicing_enabled=True,
        juice_configs=configs,
        pins=pins,
    )
    second = build_skeleton(
        duration_days=2,
        juicing_enabled=True,
        juice_configs=configs,
        pins=pins,
    )
    assert first == second
    prompt = first.to_prompt({pins[0].recipe_id: "R7"})
    assert prompt
    assert any(row["pinned"] == "R7" for row in prompt)
