"""Replay saved plan checkpoints through the resume path. No model calls.

Missing fixture files are skipped. Patricia exports them with
scripts/export_plan_checkpoint.py and does not commit from that script.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from agent.plan_generator import PlanGeneratorAgent
from db.models import CookingType, DietType, JuiceTime, RecipeType, RecipeUsagePolicy
from planning.skeleton import JuiceSlotConfig, Pin, build_skeleton
from schemas.agent import GeneratedPlanData, PlanGenerationJob
from schemas.recipes import PinnedRecipeSnapshot, RecipePlanSnapshot
from validation.layout_guard import normalize_title

from tests.unit.test_plan_invariants import assert_plan_invariants

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "plan_replay"
_PREFIXES = ("bfb0ddf0",)


class _FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("replay must not call the model")


class _Rows:
    def scalars(self) -> _Rows:
        return self

    def all(self) -> list[object]:
        return []


def _layout(plan: GeneratedPlanData) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    for day in plan.days:
        for item in day.items:
            rows.append(
                (day.day_number, item.slot_type, normalize_title(item.recipe_title))
            )
    return rows


def _checkpoint_layout(output: dict[str, object]) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    days = output.get("days")
    if not isinstance(days, list):
        return rows
    for day in days:
        if not isinstance(day, dict):
            continue
        day_number = int(day["day_number"])
        items = day.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                (
                    day_number,
                    str(item.get("slot_type")),
                    normalize_title(str(item.get("recipe_title") or "")),
                )
            )
    return rows


def _uuid_map(raw: object, *, lists: bool = False) -> dict[UUID, list[str]] | dict[UUID, str]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[UUID, list[str]] | dict[UUID, str] = {}
    for key, value in raw.items():
        try:
            recipe_id = UUID(str(key))
        except (TypeError, ValueError):
            continue
        if lists:
            names = value if isinstance(value, list) else []
            parsed[recipe_id] = [str(name) for name in names]  # type: ignore[index]
        else:
            parsed[recipe_id] = str(value or "")  # type: ignore[index]
    return parsed


@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.asyncio
async def test_replay_checkpoint_matches_layout(
    prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _FIXTURES / f"{prefix}.json"
    if not path.is_file():
        pytest.skip(
            f"Missing replay fixture {path.name}. Export it with "
            f"python -m scripts.export_plan_checkpoint --job-prefix {prefix} "
            f"--out tests/fixtures/plan_replay/{prefix}.json"
        )
    document = json.loads(path.read_text(encoding="utf-8"))
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    result, client = await _resume(document)
    assert client.calls == 0
    output = document["llm_output"]["output"]
    assert isinstance(output, dict)
    assert _layout(result) == _checkpoint_layout(output)
    skeleton = _skeleton(document)
    roles = _uuid_map(document["llm_output"].get("roles"), lists=True)
    titles = _uuid_map(document["llm_output"].get("titles"))
    types = _uuid_map(document["llm_output"].get("types"))
    params = document.get("plan_params") if isinstance(document.get("plan_params"), dict) else {}
    diet = params.get("diet_type")
    assert_plan_invariants(
        result,
        skeleton,
        plan_diet=str(diet) if diet else None,
        candidate_roles=roles,  # type: ignore[arg-type]
        candidate_titles=titles,  # type: ignore[arg-type]
        candidate_types=types,  # type: ignore[arg-type]
        pinned_slots=_pins(skeleton),
    )
    if prefix == "bfb0ddf0":
        by_time = {
            item.juice_time: item.juice_size_ml
            for day in result.days
            for item in day.items
            if item.juice_time is not None
        }
        assert by_time.get(JuiceTime.MORNING) == 500, (
            f"morning juice_size_ml is {by_time.get(JuiceTime.MORNING)}. "
            "Resume stamps the skeleton size (500 ml)."
        )
        assert by_time.get(JuiceTime.PRE_LUNCH) == 250, (
            f"pre_lunch juice_size_ml is {by_time.get(JuiceTime.PRE_LUNCH)}. "
            "Resume stamps the skeleton size (250 ml), so 500 means the backend "
            "stored the wrong size, not only a UI label."
        )


async def _resume(document: dict[str, object]) -> tuple[GeneratedPlanData, _FakeClient]:
    params = document["plan_params"]
    assert isinstance(params, dict)
    skeleton_inputs = document["skeleton_inputs"]
    assert isinstance(skeleton_inputs, dict)
    llm_output = document["llm_output"]
    assert isinstance(llm_output, dict)
    client = _FakeClient()
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(
            planning_candidates=AsyncMock(side_effect=AssertionError("re-query"))
        ),  # type: ignore[arg-type]
    )
    calorie = params.get("calorie_target")
    job = PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=int(skeleton_inputs["duration_days"]),
        diet_type=DietType(str(params["diet_type"])),
        cooking_type=CookingType(str(params["cooking_type"]))
        if params.get("cooking_type")
        else CookingType.COOKED_100,
        calorie_target=int(calorie) if calorie is not None else None,
        sourcing_policy=RecipeUsagePolicy(
            str(params.get("sourcing_policy") or "balanced")
        ),
        include_juicing=bool(skeleton_inputs["include_juicing"]),
        notes=None,
        trace_id="replay",
    )
    profile = SimpleNamespace(
        cooking_type=job.cooking_type or CookingType.COOKED_100,
        calorie_target=job.calorie_target,
        protein_g_target=None,
        carbs_g_target=None,
        fat_g_target=None,
        fiber_g_target=None,
        diet_type=job.diet_type,
    )
    pins, pinned = _pin_snapshots(skeleton_inputs)

    async def juice_configs(_plan_id: object, _db: object) -> list[JuiceSlotConfig]:
        rows = skeleton_inputs.get("juicing_config")
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

    with (
        patch("agent.plan_generator.ProfileService") as profiles,
        patch("agent.plan_generator.RecipeService") as recipes,
        patch.object(
            PlanGeneratorAgent, "_load_juice_configs", staticmethod(juice_configs)
        ),
        patch.object(
            PlanGeneratorAgent,
            "_load_pins",
            AsyncMock(return_value=(pins, pinned)),
        ),
    ):
        profiles.return_value.get_profile = AsyncMock(return_value=profile)
        profiles.return_value.get_exclusions = AsyncMock(return_value=[])
        recipes.return_value.load_plan_snapshots = AsyncMock(
            return_value=_plan_snapshots(document)
        )
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        result = await agent.generate(job, db=db, saved_llm_output=llm_output)
    return result, client


def _plan_snapshots(document: dict[str, object]) -> dict[UUID, RecipePlanSnapshot]:
    raw = document.get("snapshots")
    if not isinstance(raw, dict):
        return {}
    loaded: dict[UUID, RecipePlanSnapshot] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            recipe_id = UUID(str(key))
        except (TypeError, ValueError):
            continue
        loaded[recipe_id] = RecipePlanSnapshot.model_validate(value)
    return loaded


def _skeleton(document: dict[str, object]):
    raw = document["skeleton_inputs"]
    assert isinstance(raw, dict)
    configs: list[JuiceSlotConfig] = []
    rows = raw.get("juicing_config")
    if isinstance(rows, list):
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
    pins, _pinned = _pin_snapshots(raw)
    return build_skeleton(
        duration_days=int(raw["duration_days"]),
        juicing_enabled=bool(raw["include_juicing"]),
        juice_configs=configs or None,
        pins=pins,
    )


def _pin_snapshots(
    skeleton_inputs: dict[str, object],
) -> tuple[list[Pin], dict[UUID, PinnedRecipeSnapshot]]:
    raw = skeleton_inputs.get("pins")
    pins: list[Pin] = []
    pinned: dict[UUID, PinnedRecipeSnapshot] = {}
    if not isinstance(raw, list):
        return pins, pinned
    for row in raw:
        if not isinstance(row, dict):
            continue
        recipe_id = UUID(str(row["recipe_id"]))
        recipe_type = str(row.get("recipe_type") or "meal")
        pins.append(
            Pin(
                day_number=int(row["day"]),
                slot=str(row["slot"]),
                recipe_id=recipe_id,
                recipe_type=recipe_type,
            )
        )
        pinned[recipe_id] = PinnedRecipeSnapshot(
            recipe_id=recipe_id,
            title=str(row.get("recipe_name") or recipe_id),
            recipe_type=RecipeType(recipe_type),
            calories=None,
        )
    return pins, pinned


def _pins(skeleton):
    pinned = set()
    for slot in skeleton.slots:
        if slot.pinned_recipe_id is None:
            continue
        pinned.add(
            (
                slot.day_number,
                slot.slot,
                slot.slot_order,
                slot.pinned_recipe_id,
                slot.juice_time or "",
            )
        )
    return pinned
