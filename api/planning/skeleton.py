"""Plan skeleton built before any model call.

Juice time and size are decided here. The model fills slots; it does not
choose millilitres. No database and no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from db.models import JuiceSize

SlotKind = Literal["meal", "juice", "smoothie"]

_JUICE_KINDS = frozenset({"juice", "smoothie"})
_MEAL_SLOT_ORDER = {
    "breakfast": 0,
    "lunch": 1,
    "dinner": 2,
    "snack": 3,
    "extra_morning": 4,
    "extra_afternoon": 5,
    "extra_evening": 6,
}
_DEFAULT_JUICE = (
    ("morning", 500, 0),
    ("pre_lunch", 250, 1),
)

JUICE_SIZE_ML: dict[str, int] = {
    "shot_ml125": 125,
    "oz8_ml250": 250,
    "oz16_ml500": 500,
    "oz24_ml750": 750,
    "oz32_ml1000": 1000,
}


class SkeletonError(ValueError):
    """A pin or juicing setting cannot be turned into slots."""


def ml_for_juice_size(size: JuiceSize | str) -> int:
    key = size.value if isinstance(size, JuiceSize) else str(size)
    try:
        return JUICE_SIZE_ML[key]
    except KeyError as exc:
        raise SkeletonError(f"Unknown juice size: {key}") from exc


@dataclass(frozen=True, slots=True)
class JuiceSlotConfig:
    time_of_day: str
    size_ml: int
    slot_order: int


@dataclass(frozen=True, slots=True)
class Pin:
    day_number: int
    slot: str
    recipe_id: UUID
    recipe_type: str


@dataclass(frozen=True, slots=True)
class SkeletonSlot:
    day_number: int
    slot: str
    slot_order: int
    kind: SlotKind
    juice_time: str | None
    juice_size_ml: int | None
    pinned_recipe_id: UUID | None
    to_fill: bool


@dataclass(frozen=True, slots=True)
class PlanSkeleton:
    slots: tuple[SkeletonSlot, ...]

    def for_day(self, n: int) -> tuple[SkeletonSlot, ...]:
        return tuple(slot for slot in self.slots if slot.day_number == n)

    def to_prompt(
        self, refs: Mapping[UUID, str] | None = None
    ) -> list[dict[str, object]]:
        lookup = refs or {}
        rows: list[dict[str, object]] = []
        for slot in self.slots:
            pinned = None
            if slot.pinned_recipe_id is not None:
                pinned = lookup.get(slot.pinned_recipe_id)
            rows.append(
                {
                    "day": slot.day_number,
                    "slot": slot.slot,
                    "juice_time": slot.juice_time,
                    "size_ml": slot.juice_size_ml,
                    "pinned": pinned,
                }
            )
        return rows


def build_skeleton(
    *,
    duration_days: int,
    juicing_enabled: bool,
    juice_configs: Sequence[JuiceSlotConfig] | None,
    pins: Sequence[Pin],
    meal_slots: Sequence[str] = ("breakfast", "lunch", "dinner"),
) -> PlanSkeleton:
    """Build one deterministic slot list for the whole plan.

    Juicing off: no juice or smoothie slots; a pin on either is an error.
    Juicing on with no configs: every day gets morning 500 ml and pre_lunch 250 ml.
    Configs are used in their slot_order. A smoothie pin creates a smoothie slot.
    Slot and recipe type must match. A day with no solid meals is valid.
    """
    for pin in pins:
        kind = _kind_for_pin(pin)
        if not juicing_enabled and kind in _JUICE_KINDS:
            raise SkeletonError(
                f"Juicing is off; cannot pin a {kind} slot on day {pin.day_number}"
            )

    configs = _juice_configs(juicing_enabled, juice_configs)
    slots: list[SkeletonSlot] = []
    for day_number in range(1, duration_days + 1):
        for meal in meal_slots:
            slots.append(
                _meal_slot(day_number, meal, _MEAL_SLOT_ORDER.get(meal, 50))
            )
        for config in configs:
            slots.append(
                SkeletonSlot(
                    day_number=day_number,
                    slot="juice",
                    slot_order=config.slot_order,
                    kind="juice",
                    juice_time=config.time_of_day,
                    juice_size_ml=config.size_ml,
                    pinned_recipe_id=None,
                    to_fill=True,
                )
            )

    _apply_pins(slots, pins, juicing_enabled)
    slots.sort(
        key=lambda slot: (
            slot.day_number,
            slot.slot_order,
            slot.slot,
            slot.juice_time or "",
        )
    )
    return PlanSkeleton(slots=tuple(slots))


def _juice_configs(
    juicing_enabled: bool,
    juice_configs: Sequence[JuiceSlotConfig] | None,
) -> tuple[JuiceSlotConfig, ...]:
    if not juicing_enabled:
        return ()
    if juice_configs:
        return tuple(sorted(juice_configs, key=lambda row: (row.slot_order, row.time_of_day)))
    return tuple(
        JuiceSlotConfig(time_of_day=time_of_day, size_ml=size_ml, slot_order=order)
        for time_of_day, size_ml, order in _DEFAULT_JUICE
    )


def _meal_slot(day_number: int, slot: str, slot_order: int) -> SkeletonSlot:
    return SkeletonSlot(
        day_number=day_number,
        slot=slot,
        slot_order=slot_order,
        kind="meal",
        juice_time=None,
        juice_size_ml=None,
        pinned_recipe_id=None,
        to_fill=True,
    )


def _kind_for_pin(pin: Pin) -> str:
    slot = pin.slot
    recipe_type = pin.recipe_type
    if slot in _JUICE_KINDS or recipe_type in _JUICE_KINDS:
        if slot != recipe_type:
            raise SkeletonError(
                f"Slot '{slot}' does not match recipe type '{recipe_type}'"
            )
        return slot
    if recipe_type != "meal":
        raise SkeletonError(
            f"Slot '{slot}' does not match recipe type '{recipe_type}'"
        )
    return "meal"


def _apply_pins(
    slots: list[SkeletonSlot],
    pins: Sequence[Pin],
    juicing_enabled: bool,
) -> None:
    smoothie_counts: dict[int, int] = {}
    for pin in pins:
        kind = _kind_for_pin(pin)
        if kind == "meal":
            _pin_meal(slots, pin)
        elif kind == "juice":
            if not juicing_enabled:
                raise SkeletonError(
                    f"Juicing is off; cannot pin a juice slot on day {pin.day_number}"
                )
            _pin_juice(slots, pin)
        else:
            count = smoothie_counts.get(pin.day_number, 0)
            smoothie_counts[pin.day_number] = count + 1
            slots.append(
                SkeletonSlot(
                    day_number=pin.day_number,
                    slot="smoothie",
                    slot_order=100 + count,
                    kind="smoothie",
                    juice_time=None,
                    juice_size_ml=None,
                    pinned_recipe_id=pin.recipe_id,
                    to_fill=False,
                )
            )


def _pin_meal(slots: list[SkeletonSlot], pin: Pin) -> None:
    for index, slot in enumerate(slots):
        if slot.day_number != pin.day_number or slot.slot != pin.slot:
            continue
        if slot.kind != "meal":
            continue
        if slot.pinned_recipe_id not in (None, pin.recipe_id):
            raise SkeletonError(
                f"Day {pin.day_number} {pin.slot} is already pinned"
            )
        slots[index] = _with_pin(slot, pin.recipe_id)
        return
    slots.append(
        _with_pin(
            _meal_slot(
                pin.day_number,
                pin.slot,
                _MEAL_SLOT_ORDER.get(pin.slot, 50),
            ),
            pin.recipe_id,
        )
    )


def _pin_juice(slots: list[SkeletonSlot], pin: Pin) -> None:
    for index, slot in enumerate(slots):
        if slot.day_number != pin.day_number or slot.kind != "juice":
            continue
        if slot.pinned_recipe_id is not None:
            continue
        slots[index] = _with_pin(slot, pin.recipe_id)
        return
    raise SkeletonError(f"No juice slot available for pin on day {pin.day_number}")


def _with_pin(slot: SkeletonSlot, recipe_id: UUID) -> SkeletonSlot:
    return SkeletonSlot(
        day_number=slot.day_number,
        slot=slot.slot,
        slot_order=slot.slot_order,
        kind=slot.kind,
        juice_time=slot.juice_time,
        juice_size_ml=slot.juice_size_ml,
        pinned_recipe_id=recipe_id,
        to_fill=False,
    )
