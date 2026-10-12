"""The model sees R refs. Unknown refs retry once and are never inserted."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from agent.plan_generator import PlanGeneratorAgent, _plan_tool
from db.models import CookingType, DietType, RecipeUsagePolicy
from exceptions import PlanGenerationFailedError
from schemas.agent import PlanGenerationJob
from schemas.recipes import RecipePlanSnapshot


def _job() -> PlanGenerationJob:
    return PlanGenerationJob(
        user_id=uuid4(),
        plan_id=uuid4(),
        duration_days=1,
        diet_type=DietType.PLANT_BASED,
        cooking_type=CookingType.COOKED_100,
        calorie_target=2000,
        sourcing_policy=RecipeUsagePolicy.BALANCED,
        include_juicing=False,
        notes=None,
        trace_id="handles",
    )


def _profile() -> SimpleNamespace:
    return SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=2000,
        protein_g_target=80,
        carbs_g_target=250,
        fat_g_target=70,
        fiber_g_target=30,
    )


class _Rows:
    def scalars(self) -> _Rows:
        return self

    def all(self) -> list[object]:
        return []


def _recipe(title: str, slot: str) -> dict[str, object]:
    return {
        "title": title,
        "slot_type": slot,
        "diet_type": "plant_based",
        "prep_type": "steamed",
        "servings": 1,
        "primary_protein": "none",
        "ingredients": [{"ingredient_name": "oats", "quantity": 1, "unit": "cup"}],
        "steps": [{"step_number": 1, "instruction": "Cook."}],
        "nutrition_per_serving": {
            "calories_kcal": 670,
            "protein_g": 27,
            "fat_g": 23,
            "carbohydrates_g": 83,
            "fiber_g": 10,
        },
    }


def _day(items: list[dict[str, object]]) -> dict[str, object]:
    return {"days": [{"day_number": 1, "items": items}], "generated_recipes": []}


class _Client:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self.calls = 0
        self.payload = payload

    async def complete(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        if self.payload is None:
            raise AssertionError("model must not be called")
        block = SimpleNamespace(type="tool_use", name="output_plan", input=self.payload)
        return SimpleNamespace(
            content=[block],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )


def _agent(client: _Client) -> PlanGeneratorAgent:
    return PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=SimpleNamespace(planning_candidates=AsyncMock(return_value=[])),  # type: ignore[arg-type]
    )


def _patches():
    profiles = patch("agent.plan_generator.ProfileService")
    recipes = patch("agent.plan_generator.RecipeService")
    return profiles, recipes


def test_plan_tool_enum_is_the_handle_list() -> None:
    first = uuid4()
    second = uuid4()
    tool = _plan_tool({"R1": first, "R2": second})
    enum = tool["input_schema"]["$defs"]["GeneratedPlanItemAI"]["properties"]["recipe_id"][
        "enum"
    ]
    assert enum == ["R1", "R2", "generate_new"]
    empty = _plan_tool({})
    empty_enum = empty["input_schema"]["$defs"]["GeneratedPlanItemAI"]["properties"][
        "recipe_id"
    ]["enum"]
    assert empty_enum == ["generate_new"]


def test_extract_maps_handles_back_to_uuids() -> None:
    recipe_id = uuid4()
    message = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="output_plan",
                input={
                    "days": [
                        {
                            "day_number": 1,
                            "items": [
                                {
                                    "slot_type": "breakfast",
                                    "recipe_id": "R1",
                                    "recipe_title": "Oats",
                                    "servings": 1,
                                }
                            ],
                        }
                    ],
                    "generated_recipes": [],
                },
            )
        ]
    )
    plan = PlanGeneratorAgent(client=SimpleNamespace())._extract_plan(  # type: ignore[arg-type]
        message, {"R1": recipe_id}
    )
    assert plan.days[0].items[0].recipe_id == recipe_id


def _clean_day() -> dict[str, object]:
    items: list[dict[str, object]] = []
    recipes: list[dict[str, object]] = []
    for slot, title in (
        ("breakfast", "Oats"),
        ("lunch", "Salad"),
        ("dinner", "Steaks"),
    ):
        items.append(
            {
                "slot_type": slot,
                "recipe_id": "generate_new",
                "recipe_title": title,
                "servings": 1,
            }
        )
        recipes.append(_recipe(title, slot))
    return {"days": [{"day_number": 1, "items": items}], "generated_recipes": recipes}


def _salmon_twice() -> dict[str, object]:
    return {
        "days": [
            {
                "day_number": 1,
                "items": [
                    {
                        "slot_type": "lunch",
                        "recipe_id": "generate_new",
                        "recipe_title": "Salmon",
                        "servings": 1,
                    },
                    {
                        "slot_type": "dinner",
                        "recipe_id": "generate_new",
                        "recipe_title": "Salmon",
                        "servings": 1,
                    },
                ],
            }
        ],
        "generated_recipes": [_recipe("Salmon", "dinner")],
    }


def _juice_twice() -> dict[str, object]:
    return {
        "days": [
            {
                "day_number": 1,
                "items": [
                    {
                        "slot_type": "juice",
                        "recipe_id": "generate_new",
                        "recipe_title": "Green",
                        "servings": 1,
                    },
                    {
                        "slot_type": "extra_morning",
                        "recipe_id": "generate_new",
                        "recipe_title": "Green",
                        "servings": 1,
                    },
                ],
            }
        ],
        "generated_recipes": [_recipe("Green", "juice")],
    }


class _RetryClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.calls = 0
        self.payload = payload
        self.seen: list[object] = []

    async def complete(self, messages: object, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        self.seen.append(messages)
        block = SimpleNamespace(
            type="tool_use",
            name="output_plan",
            id="toolu_layout",
            input=self.payload,
        )
        return SimpleNamespace(
            content=[block],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )


@pytest.mark.asyncio
async def test_guard_error_retries_then_fails_on_the_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    client = _RetryClient(_juice_twice())
    agent = _agent(client)  # type: ignore[arg-type]
    profiles, recipes = _patches()
    wrote = AsyncMock()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        with pytest.raises(PlanGenerationFailedError, match="Layout:"):
            await agent.generate(_job(), db=db, on_llm_output=wrote)
    assert client.calls == 2
    assert "Layout" in str(client.seen[1])
    wrote.assert_not_called()


@pytest.mark.asyncio
async def test_same_juice_twice_retries_once_then_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    client = _Client(_juice_twice())
    agent = _agent(client)
    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        with pytest.raises(PlanGenerationFailedError, match="Layout:"):
            await agent.generate(_job(), db=db)
    assert client.calls == 2


@pytest.mark.asyncio
async def test_same_day_repeat_retries_once_then_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    client = _Client(_salmon_twice())
    agent = _agent(client)
    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        with pytest.raises(PlanGenerationFailedError, match="Layout:"):
            await agent.generate(_job(), db=db)
    assert client.calls == 2


@pytest.mark.asyncio
async def test_bad_layout_in_checkpoint_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    salmon = uuid4()
    saved = {
        "output": {
            "days": [
                {
                    "day_number": 1,
                    "items": [
                        {
                            "slot_type": "lunch",
                            "recipe_id": str(salmon),
                            "recipe_title": "Salmon",
                            "servings": 1,
                        },
                        {
                            "slot_type": "dinner",
                            "recipe_id": str(salmon),
                            "recipe_title": "Salmon",
                            "servings": 1,
                        },
                    ],
                }
            ],
            "generated_recipes": [],
        },
        "handles": {"R1": str(salmon)},
    }
    client = _Client(None)
    agent = _agent(client)
    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        wrote = AsyncMock()
        with pytest.raises(PlanGenerationFailedError, match="Layout:"):
            await agent.generate(
                _job(), db=db, saved_llm_output=saved, on_llm_output=wrote
            )
    assert client.calls == 0
    wrote.assert_not_called()


def _resumed_day(recipe_id: UUID) -> dict[str, object]:
    return {
        "output": {
            "days": [
                {
                    "day_number": 1,
                    "items": [
                        {
                            "slot_type": "breakfast",
                            "recipe_id": str(recipe_id),
                            "recipe_title": "Oats",
                            "servings": 1,
                        },
                        {
                            "slot_type": "lunch",
                            "recipe_id": "generate_new",
                            "recipe_title": "Salad",
                            "servings": 1,
                        },
                        {
                            "slot_type": "dinner",
                            "recipe_id": "generate_new",
                            "recipe_title": "Steaks",
                            "servings": 1,
                        },
                    ],
                }
            ],
            "generated_recipes": [
                _recipe("Salad", "lunch"),
                _recipe("Steaks", "dinner"),
            ],
        },
        "handles": {"R1": str(recipe_id)},
    }


class _LayoutRows:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


@pytest.mark.asyncio
async def test_resume_uses_checkpoint_roles_without_requery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    oats = uuid4()
    saved = _resumed_day(oats)
    saved["roles"] = {str(oats): ["breakfast"]}
    saved["titles"] = {str(oats): "Oats"}
    search = SimpleNamespace(
        planning_candidates=AsyncMock(side_effect=AssertionError("re-query"))
    )
    client = _Client(None)
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=search,  # type: ignore[arg-type]
    )
    snapshot = RecipePlanSnapshot(
        recipe_id=oats,
        title="Oats",
        calories=400,
        protein_g=12,
        carbs_g=50,
        fat_g=10,
        fiber_g=6,
        ingredients=[],
    )
    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(
            return_value={oats: snapshot}
        )
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        result = await agent.generate(_job(), db=db, saved_llm_output=saved)
    assert client.calls == 0
    search.planning_candidates.assert_not_called()
    assert result.days[0].items[0].recipe_id == oats


@pytest.mark.asyncio
async def test_resume_without_checkpoint_maps_loads_from_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    oats = uuid4()
    saved = _resumed_day(oats)
    search = SimpleNamespace(
        planning_candidates=AsyncMock(side_effect=AssertionError("re-query"))
    )
    client = _Client(None)
    agent = PlanGeneratorAgent(
        client=client,  # type: ignore[arg-type]
        recipe_search=search,  # type: ignore[arg-type]
    )
    snapshot = RecipePlanSnapshot(
        recipe_id=oats,
        title="Oats",
        calories=400,
        protein_g=12,
        carbs_g=50,
        fat_g=10,
        fiber_g=6,
        ingredients=[],
    )
    layout_sql: list[str] = []

    async def execute(stmt: object, *_args: object, **_kwargs: object) -> object:
        text = str(stmt)
        if "recipe_meal_details" in text:
            layout_sql.append(text)
            return _LayoutRows([(oats, "Oats", ["breakfast"])])
        return _Rows()

    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(
            return_value={oats: snapshot}
        )
        db = AsyncMock()
        db.execute = execute
        result = await agent.generate(_job(), db=db, saved_llm_output=saved)
    assert client.calls == 0
    search.planning_candidates.assert_not_called()
    assert layout_sql
    assert "user_id" in layout_sql[0]
    assert "deleted_at" in layout_sql[0]
    assert result.days[0].items[0].recipe_title == "Oats"


@pytest.mark.asyncio
async def test_clean_layout_is_one_call_and_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.plan_generator.settings.plan_assigner_polish", False)
    client = _Client(_clean_day())
    agent = _agent(client)
    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        result = await agent.generate(_job(), db=db)
    assert client.calls == 1
    by_slot = {item.slot_type: item.recipe_title for item in result.days[0].items}
    assert by_slot == {
        "breakfast": "Oats",
        "lunch": "Salad",
        "dinner": "Steaks",
    }


@pytest.mark.asyncio
async def test_unknown_handle_retries_once_then_fails() -> None:
    payload = _day(
        [
            {
                "slot_type": "breakfast",
                "recipe_id": "R99",
                "recipe_title": "Nope",
                "servings": 1,
            }
        ]
    )
    client = _Client(payload)
    agent = _agent(client)
    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        with pytest.raises(PlanGenerationFailedError, match="Unknown recipe ref"):
            await agent.generate(_job(), db=db)
    assert client.calls == 2


@pytest.mark.asyncio
async def test_resume_uses_the_saved_handle_map() -> None:
    recipe_id = uuid4()
    lunch = _recipe("Lunch", "lunch")
    dinner = _recipe("Dinner", "dinner")
    saved = {
        "output": {
            "days": [
                {
                    "day_number": 1,
                    "items": [
                        {
                            "slot_type": "breakfast",
                            "recipe_id": str(recipe_id),
                            "recipe_title": "Oats",
                            "servings": 1,
                        },
                        {
                            "slot_type": "lunch",
                            "recipe_id": "generate_new",
                            "recipe_title": "Lunch",
                            "servings": 1,
                        },
                        {
                            "slot_type": "dinner",
                            "recipe_id": "generate_new",
                            "recipe_title": "Dinner",
                            "servings": 1,
                        },
                    ],
                }
            ],
            "generated_recipes": [lunch, dinner],
        },
        "handles": {"R1": str(recipe_id)},
        "roles": {str(recipe_id): ["breakfast"]},
        "titles": {str(recipe_id): "Oats"},
        "types": {str(recipe_id): "meal"},
    }
    client = _Client(None)
    agent = _agent(client)
    agent._assigner.assign = lambda *_args, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        feasible=False,
        days=[],
        errors=["kept"],
        warnings=[],
    )
    snapshot = RecipePlanSnapshot(
        recipe_id=recipe_id,
        title="Oats",
        calories=400,
        protein_g=12,
        carbs_g=50,
        fat_g=10,
        fiber_g=6,
        ingredients=[],
    )
    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(
            return_value={recipe_id: snapshot}
        )
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        result = await agent.generate(_job(), db=db, saved_llm_output=saved)
    assert client.calls == 0
    breakfast = result.days[0].items[0]
    assert breakfast.recipe_id == recipe_id


@pytest.mark.asyncio
async def test_legacy_checkpoint_fails_with_zero_model_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agent.plan_generator.settings.plan_resume_legacy_checkpoint", "fail"
    )
    client = _Client(None)
    agent = _agent(client)
    profiles, recipes = _patches()
    legacy = {
        "days": [
            {
                "day_number": 1,
                "items": [
                    {
                        "slot_type": "breakfast",
                        "recipe_id": "generate_new",
                        "recipe_title": "Oats",
                        "servings": 1,
                    }
                ],
            }
        ],
        "generated_recipes": [_recipe("Oats", "breakfast")],
    }
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        with pytest.raises(PlanGenerationFailedError, match="handle map"):
            await agent.generate(_job(), db=db, saved_llm_output=legacy)
    assert client.calls == 0


@pytest.mark.asyncio
async def test_fresh_raw_uuid_retries_once_then_fails() -> None:
    raw_id = str(uuid4())
    payload = _day(
        [
            {
                "slot_type": "breakfast",
                "recipe_id": raw_id,
                "recipe_title": "Hers",
                "servings": 1,
            }
        ]
    )
    client = _Client(payload)
    agent = _agent(client)
    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        with pytest.raises(PlanGenerationFailedError, match="Unknown recipe ref"):
            await agent.generate(_job(), db=db)
    assert client.calls == 2


@pytest.mark.asyncio
async def test_resume_rejects_uuid_missing_from_the_handle_map() -> None:
    client = _Client(None)
    agent = _agent(client)
    saved = {
        "output": {
            "days": [
                {
                    "day_number": 1,
                    "items": [
                        {
                            "slot_type": "breakfast",
                            "recipe_id": str(uuid4()),
                            "recipe_title": "Oats",
                            "servings": 1,
                        }
                    ],
                }
            ],
            "generated_recipes": [],
        },
        "handles": {"R1": str(uuid4())},
    }
    profiles, recipes = _patches()
    with profiles as profile_cls, recipes as recipe_cls:
        profile_cls.return_value.get_profile = AsyncMock(return_value=_profile())
        profile_cls.return_value.get_exclusions = AsyncMock(return_value=[])
        recipe_cls.return_value.load_plan_snapshots = AsyncMock(return_value={})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Rows())
        with pytest.raises(PlanGenerationFailedError, match="unmapped"):
            await agent.generate(_job(), db=db, saved_llm_output=saved)
    assert client.calls == 0
