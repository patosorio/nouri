"""Golden plan cases. The model is mocked. Each case is one JSON file."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from agent.plan_generator import PlanGeneratorAgent
from db.models import CookingType, DietType, RecipeType, RecipeUsagePolicy
from exceptions import PlanGenerationFailedError
from planning.skeleton import JuiceSlotConfig, Pin, build_skeleton
from schemas.agent import GeneratedPlanData, PlanGenerationJob
from schemas.recipes import PinnedRecipeSnapshot
from validation.layout_guard import slot_kind

from tests.unit.test_plan_invariants import assert_plan_invariants

_CASES = Path(__file__).resolve().parent / "plans"


class _Client:
    def __init__(self, attempts: list[dict[str, object]]) -> None:
        self.attempts = attempts
        self.calls = 0

    async def complete(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        if self.calls > 2:
            raise AssertionError("plan generation billed a third model call")
        payload = self.attempts[min(self.calls, len(self.attempts)) - 1]
        block = SimpleNamespace(type="tool_use", name="output_plan", input=payload)
        return SimpleNamespace(
            content=[block],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )


class _Rows:
    def scalars(self) -> _Rows:
        return self

    def all(self) -> list[object]:
        return []


def _case_paths() -> list[pytest.ParameterSet]:
    paths = sorted(_CASES.glob("*.json"))
    params: list[pytest.ParameterSet] = []
    for path in paths:
        case = json.loads(path.read_text(encoding="utf-8"))
        marks: list[pytest.MarkDecorator] = []
        reason = case.get("xfail")
        if isinstance(reason, str) and reason:
            marks.append(pytest.mark.xfail(reason=reason))
        params.append(pytest.param(path, id=str(case["name"]), marks=marks))
    return params


@pytest.mark.parametrize("path", _case_paths())
@pytest.mark.asyncio
async def test_golden_plan(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    result, client, _agent = await _run(case)
    assert client.calls == case["expected_calls"]
    verdict = case["verdict"]
    if verdict == "reject":
        assert result is None
        return
    assert result is not None
    if verdict == "flag":
        blob = (result.review_notes or "") + "\n" + "\n".join(_agent.dish_flags)
        assert case["flag"] in blob
    elif verdict != "accept":
        raise AssertionError(f"unknown verdict {verdict}")
    assert _layout(result, case) == case["layout"]
    skeleton = _skeleton(case)
    pins = _pins(case)
    assert_plan_invariants(
        result,
        skeleton,
        plan_diet=str(case["params"]["diet"]),
        pinned_slots=set(pins),
        candidate_types={pin[3]: pin_type for pin, pin_type in _pin_types(case)},
        candidate_titles={pin[3]: title for pin, title in _pin_titles(case)},
        candidate_roles={
            pin.recipe_id: ["breakfast"] if pin.slot == "breakfast" else [pin.slot]
            for pin in _pin_objects(case)
        },
    )


async def _run(
    case: dict[str, object],
) -> tuple[GeneratedPlanData | None, _Client, PlanGeneratorAgent]:
    attempts = case["attempts"]
    assert isinstance(attempts, list)
    client = _Client(attempts)
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(planning_candidates=AsyncMock(return_value=[])),  # type: ignore[arg-type]
    )
    params = case["params"]
    assert isinstance(params, dict)
    skeleton_inputs = case["skeleton_inputs"]
    assert isinstance(skeleton_inputs, dict)
    targets = params.get("targets") if isinstance(params.get("targets"), dict) else {}
    calorie = targets.get("calorie_target") if isinstance(targets, dict) else None
    diet = DietType(str(params["diet"]))
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=int(skeleton_inputs["duration_days"]),
        diet_type=diet,
        cooking_type=CookingType.COOKED_100,
        calorie_target=int(calorie) if calorie is not None else None,
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=bool(skeleton_inputs["include_juicing"]),
        trace_id="golden",
    )
    per_day = _items_per_day(case)
    profile = SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=job.calorie_target,
        protein_g_target=20 * per_day,
        carbs_g_target=30 * per_day,
        fat_g_target=10 * per_day,
        fiber_g_target=5 * per_day,
        diet_type=diet,
    )
    pin_rows, pinned = _pin_snapshots(skeleton_inputs)

    async def juice_configs(_plan_id: object, _db: object) -> list[JuiceSlotConfig]:
        return _juice_configs(skeleton_inputs)

    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
        patch.object(
            PlanGeneratorAgent, "_load_juice_configs", staticmethod(juice_configs)
        ),
        patch.object(
            PlanGeneratorAgent, "_load_pins", AsyncMock(return_value=(pin_rows, pinned))
        ),
    ):
        profiles.return_value.get_profile = AsyncMock(return_value=profile)
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        try:
            result = await agent.generate(job, db=db)
        except PlanGenerationFailedError as exc:
            if case["verdict"] != "reject":
                raise
            assert case["error"] in str(exc)
            return None, client, agent
    if case["verdict"] == "reject":
        raise AssertionError(f"{case['name']} was accepted")
    return result, client, agent


def _layout(plan: GeneratedPlanData, case: dict[str, object]) -> list[dict[str, object]]:
    generated = {
        recipe.title.strip().casefold(): slot_kind(recipe.slot_type)
        for recipe in plan.generated_recipes
    }
    pin_types = {
        str(row["title"]).strip().casefold(): str(row["recipe_type"])
        for row in _pin_dicts(case)
    }
    rows: list[dict[str, object]] = []
    for day in plan.days:
        for item in day.items:
            key = item.recipe_title.strip().casefold()
            rows.append(
                {
                    "day": day.day_number,
                    "slot": item.slot_type,
                    "juice_time": item.juice_time.value if item.juice_time else None,
                    "juice_size_ml": item.juice_size_ml,
                    "recipe": item.recipe_title,
                    "recipe_type": generated.get(key) or pin_types.get(key) or "meal",
                }
            )
    return rows


def _skeleton(case: dict[str, object]):
    raw = case["skeleton_inputs"]
    assert isinstance(raw, dict)
    return build_skeleton(
        duration_days=int(raw["duration_days"]),
        juicing_enabled=bool(raw["include_juicing"]),
        juice_configs=_juice_configs(raw) or None,
        pins=_pin_objects(case),
    )


def _juice_configs(raw: dict[str, object]) -> list[JuiceSlotConfig]:
    rows = raw.get("juicing_config")
    if not isinstance(rows, list):
        return []
    configs: list[JuiceSlotConfig] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        configs.append(
            JuiceSlotConfig(
                time_of_day=str(row["time_of_day"]),
                size_ml=int(row["size_ml"]),
                slot_order=int(row["slot_order"]),
            )
        )
    return configs


def _pin_dicts(case: dict[str, object]) -> list[dict[str, object]]:
    raw = case["skeleton_inputs"]
    assert isinstance(raw, dict)
    rows = raw.get("pins")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _pin_objects(case: dict[str, object]) -> list[Pin]:
    pins: list[Pin] = []
    for row in _pin_dicts(case):
        pins.append(
            Pin(
                day_number=int(row["day"]),
                slot=str(row["slot"]),
                recipe_id=UUID(str(row["recipe_id"])),
                recipe_type=str(row["recipe_type"]),
            )
        )
    return pins


def _pins(skeleton_case: dict[str, object]):
    from agent.plan_generator import PlanGeneratorAgent as Agent

    skeleton = _skeleton(skeleton_case)
    return Agent._layout_pins(skeleton)


def _pin_types(case: dict[str, object]) -> list[tuple[tuple[object, ...], str]]:
    skeleton_pins = _pins(case)
    by_id = {UUID(str(row["recipe_id"])): str(row["recipe_type"]) for row in _pin_dicts(case)}
    return [(pin, by_id[pin[3]]) for pin in skeleton_pins if pin[3] in by_id]


def _pin_titles(case: dict[str, object]) -> list[tuple[tuple[object, ...], str]]:
    skeleton_pins = _pins(case)
    by_id = {UUID(str(row["recipe_id"])): str(row["title"]) for row in _pin_dicts(case)}
    return [(pin, by_id[pin[3]]) for pin in skeleton_pins if pin[3] in by_id]


def _pin_snapshots(
    raw: dict[str, object],
) -> tuple[list[Pin], dict[UUID, PinnedRecipeSnapshot]]:
    rows = raw.get("pins")
    pins: list[Pin] = []
    pinned: dict[UUID, PinnedRecipeSnapshot] = {}
    if not isinstance(rows, list):
        return pins, pinned
    for row in rows:
        if not isinstance(row, dict):
            continue
        recipe_id = UUID(str(row["recipe_id"]))
        recipe_type = RecipeType(str(row["recipe_type"]))
        pins.append(
            Pin(
                day_number=int(row["day"]),
                slot=str(row["slot"]),
                recipe_id=recipe_id,
                recipe_type=recipe_type.value,
            )
        )
        pinned[recipe_id] = PinnedRecipeSnapshot(
            recipe_id=recipe_id,
            title=str(row["title"]),
            recipe_type=recipe_type,
            calories=290,
            protein_g=20,
            carbs_g=30,
            fat_g=10,
            fiber_g=5,
        )
    return pins, pinned


def _items_per_day(case: dict[str, object]) -> int:
    raw = case["skeleton_inputs"]
    assert isinstance(raw, dict)
    count = 3
    if raw.get("include_juicing"):
        rows = raw.get("juicing_config")
        count += len(rows) if isinstance(rows, list) and rows else 2
    return count
