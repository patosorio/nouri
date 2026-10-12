"""Plan job version stamps. No network."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from agent.plan_generator import plan_system_prompt
from agent.versions import (
    _compute_code_hash,
    plan_versions,
    prompt_version,
    schema_version,
)
from config import AgentTask, route_model
from db.models import CookingType, DietType
from services.job_service import JobService
from worker.handlers import handle_plan_generation
from worker.main import _git_state


def _good_plan() -> dict[str, object]:
    recipes = []
    items = []
    for slot in ("breakfast", "lunch", "dinner"):
        title = slot.title()
        items.append(
            {
                "slot_type": slot,
                "recipe_id": "generate_new",
                "recipe_title": title,
                "servings": 1,
            }
        )
        recipes.append(
            {
                "title": title,
                "slot_type": slot,
                "diet_type": "vegan",
                "prep_type": "steamed",
                "servings": 1,
                "primary_protein": "none",
                "ingredients": [{"ingredient_name": title, "quantity": 1, "unit": "cup"}],
                "steps": [{"step_number": 1, "instruction": "Cook."}],
                "nutrition_per_serving": {
                    "calories_kcal": 290,
                    "protein_g": 20,
                    "fat_g": 10,
                    "carbohydrates_g": 30,
                    "fiber_g": 5,
                },
            }
        )
    return {"days": [{"day_number": 1, "items": items}], "generated_recipes": recipes}


def test_prompt_version_changes_when_the_prompt_text_changes() -> None:
    original = plan_system_prompt(3, DietType.PESCATARIAN)
    assert prompt_version(original) != prompt_version(original + "\n")
    assert len(schema_version()) == 12
    stamped = plan_versions(original)
    assert stamped["prompt_version"] == prompt_version(original)
    assert stamped["schema_version"] == schema_version()
    assert stamped["model"] == route_model(AgentTask.PLAN_GENERATION)
    assert stamped["code_version"]
    assert len(stamped["code_hash"]) == 12


def test_code_hash_is_stable_and_changes_with_file_contents(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "b.py").write_text("y = 1\n", encoding="utf-8")
    skipped = tmp_path / "tests"
    skipped.mkdir()
    (skipped / "hidden.py").write_text("ignored = True\n", encoding="utf-8")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "site.py").write_text("ignored = True\n", encoding="utf-8")

    first = _compute_code_hash(tmp_path)
    assert first == _compute_code_hash(tmp_path)
    assert len(first) == 12
    assert first == _compute_code_hash(tmp_path)

    (tmp_path / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert _compute_code_hash(tmp_path) != first


def test_git_state_reports_dirty_when_git_is_reachable() -> None:
    sha, dirty = _git_state()
    assert sha
    assert dirty is None or isinstance(dirty, bool)


@pytest.mark.asyncio
async def test_plan_job_stores_versions_on_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: dict[str, object] = {}
    completed: dict[str, object] = {}
    plan = SimpleNamespace(
        id=uuid4(),
        status=SimpleNamespace(value="reviewing"),
        title="Week",
        generation_params={"duration_days": 1},
    )

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def complete(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            block = SimpleNamespace(
                type="tool_use", name="output_plan", input=_good_plan()
            )
            return SimpleNamespace(
                content=[block],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    profile = SimpleNamespace(
        cooking_type=CookingType.COOKED_100,
        calorie_target=870,
        protein_g_target=60,
        carbs_g_target=90,
        fat_g_target=30,
        fiber_g_target=15,
        diet_type=DietType.VEGAN,
    )
    monkeypatch.setattr("agent.plan_generator.AnthropicClient", FakeClient)
    search = MagicMock()
    search.planning_candidates = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "agent.plan_generator.RecipeSearchService", MagicMock(return_value=search)
    )
    profiles = MagicMock()
    profiles.get_profile = AsyncMock(return_value=profile)
    profiles.get_exclusions = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "agent.plan_generator.ProfileService", MagicMock(return_value=profiles)
    )
    recipes = MagicMock()
    recipes.load_plan_snapshots = AsyncMock(return_value={})
    recipes.list_recipes = AsyncMock(return_value=SimpleNamespace(data=[]))
    monkeypatch.setattr(
        "agent.plan_generator.RecipeService", MagicMock(return_value=recipes)
    )
    monkeypatch.setattr(
        "worker.handlers.RecipeService",
        MagicMock(
            return_value=MagicMock(
                save_generated_batch=AsyncMock(
                    return_value=SimpleNamespace(recipes=[], inserted=[], id_remap={})
                )
            )
        ),
    )
    plan_service = MagicMock()
    plan_service.write_generated_plan = AsyncMock(return_value=plan)
    plan_service._assert_recipes_owned = AsyncMock()
    monkeypatch.setattr(
        "worker.handlers.PlanService", MagicMock(return_value=plan_service)
    )
    monkeypatch.setattr(
        "worker.handlers.NotificationService",
        MagicMock(return_value=MagicMock(publish=AsyncMock())),
    )
    monkeypatch.setattr(JobService, "set_progress", AsyncMock())

    async def save_llm_output(_self: object, _job_id: object, payload: dict[str, object]) -> None:
        saved["payload"] = payload

    async def mark_complete(
        _self: object, _job_id: object, result: dict[str, object], _db: object
    ) -> None:
        completed["result"] = result

    monkeypatch.setattr(JobService, "save_llm_output", save_llm_output)
    monkeypatch.setattr(JobService, "mark_complete", mark_complete)

    job = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=uuid4(),
        job_type="generate_plan",
        llm_output=None,
        result=None,
        payload={
            "params": {
                "duration_days": 1,
                "diet_type": "vegan",
                "cooking_type": "cooked_100",
                "calorie_target": 870,
            },
            "trace_id": "versions",
        },
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=list), all=list))
    await handle_plan_generation(job, db)

    expected = plan_versions(plan_system_prompt(1, DietType.VEGAN))
    checkpoint = saved["payload"]
    assert isinstance(checkpoint, dict)
    result = completed["result"]
    assert isinstance(result, dict)
    assert checkpoint["versions"] == expected
    assert result["versions"] == expected
    assert plan.generation_params["versions"] == expected
    assert set(expected) == {
        "code_version",
        "code_hash",
        "prompt_version",
        "schema_version",
        "model",
    }

    failed = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=uuid4(),
        job_type="generate_plan",
        llm_output=None,
        result=None,
        payload=job.payload,
    )

    async def fail_complete(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a layout failure must not complete")

    class BadClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def complete(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            payload = _good_plan()
            days = payload["days"]
            assert isinstance(days, list)
            day = days[0]
            assert isinstance(day, dict)
            items = day["items"]
            assert isinstance(items, list)
            day["items"] = [item for item in items if item["slot_type"] != "dinner"]  # type: ignore[index]
            block = SimpleNamespace(type="tool_use", name="output_plan", input=payload)
            return SimpleNamespace(
                content=[block],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    monkeypatch.setattr("agent.plan_generator.AnthropicClient", BadClient)
    monkeypatch.setattr(JobService, "mark_complete", fail_complete)
    monkeypatch.setattr(JobService, "mark_failed", AsyncMock(return_value=True))
    from exceptions import PlanGenerationFailedError

    with pytest.raises(PlanGenerationFailedError):
        await handle_plan_generation(failed, db)
    assert failed.result["versions"] == expected
