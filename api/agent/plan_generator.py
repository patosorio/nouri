"""PlanGeneratorAgent — docs/7_TECH_SPEC.md §5.4 / RISK-07."""

from __future__ import annotations

import copy
import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from config import AgentTask, route_model, settings
from db.models import (
    DietType,
    JuiceTime,
    JuicingConfig,
    PreparationType,
    Recipe,
    RecipeMealDetails,
)
from exceptions import NutritionOutOfRangeError, PlanGenerationFailedError
from planning.skeleton import (
    JuiceSlotConfig,
    Pin,
    PlanSkeleton,
    SkeletonError,
    SkeletonSlot,
    build_skeleton,
    ml_for_juice_size,
)
from preprocessing.exclusion_service import ExclusionService
from preprocessing.notes_preprocessor import NotesPreprocessor, RecipeTitleRef
from schemas.agent import (
    GeneratedPlanData,
    GeneratedPlanDayAI,
    GeneratedPlanItemAI,
    GeneratedRecipeAI,
    PlanGenerationJob,
)
from schemas.recipes import PinnedRecipeSnapshot
from search.recipe_search_service import RecipeCandidate, RecipeSearchService
from services.profile_service import ProfileService
from services.recipe_service import RecipeService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from validation.dish_guards import (
    DayTotals,
    DishNutrition,
    ServingNutrition,
    check_day_totals,
    check_dish_nutrition,
    grams_from_ingredients,
    hard_dish_flags,
)
from validation.exclusion_checker import ExclusionChecker
from validation.layout_guard import (
    PinnedSlot,
    check_layout,
    consecutive_main_dish_notes,
    match_skeleton,
    normalize_title,
)
from validation.nutrition_validator import NutritionValidator
from validation.plan_validator import PlanValidator
from validation.slot_assigner import AssignableRecipe, SlotAssigner, SlotSpec
from validation.types import (
    ExclusionView,
    MacroTargets,
    NutritionPerServing,
    PlanDayView,
    PlanDraftView,
    PlanItemView,
    RecipeIngredientView,
    RecipeView,
    UserProfileView,
)

from agent.client import AnthropicClient, attempt_fits

logger = structlog.get_logger(__name__)

PlanProgressFn = Callable[[int, str, int, int], Awaitable[None]]
LlmOutputFn = Callable[[dict[str, Any]], Awaitable[None]]
ModelStartFn = Callable[[], Awaitable[None]]


def _nutrition_unknown_ids(plan: GeneratedPlanData) -> set[UUID]:
    ids: set[UUID] = set()
    for day in plan.days:
        for item in day.items:
            if item.nutrition_unknown and isinstance(item.recipe_id, UUID):
                ids.add(item.recipe_id)
    return ids


async def _emit_progress(
    on_progress: PlanProgressFn | None,
    progress_pct: int,
    stage: str,
    days_completed: int,
    days_total: int,
) -> None:
    if on_progress is not None:
        await on_progress(progress_pct, stage, days_completed, days_total)


def _plan_output_schema() -> dict[str, Any]:
    schema = GeneratedPlanData.model_json_schema()
    defs = schema.get("$defs") or schema.get("definitions") or {}
    snapshot_fields = (
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
        "prep_method",
        "primary_protein",
        "juice_size_ml",
        "nutrition_unknown",
    )
    for name, defn in defs.items():
        if not isinstance(defn, dict):
            continue
        props = defn.get("properties")
        if not isinstance(props, dict):
            continue
        props.pop("assigned_id", None)
        if name == "GeneratedPlanItemAI":
            for field in snapshot_fields:
                props.pop(field, None)
            required = defn.get("required")
            if isinstance(required, list):
                defn["required"] = [r for r in required if r not in snapshot_fields]
    return schema


def _plan_tool(handles: Mapping[str, UUID]) -> dict[str, Any]:
    """output_plan tool whose recipe_id enum is this call's R handles."""
    schema = _plan_output_schema()
    enum_values = [*handles.keys(), "generate_new"] if handles else ["generate_new"]
    defs = schema.get("$defs") or schema.get("definitions") or {}
    item = defs.get("GeneratedPlanItemAI")
    if isinstance(item, dict):
        props = item.get("properties")
        if isinstance(props, dict):
            props["recipe_id"] = {"type": "string", "enum": enum_values}
    return {
        "name": "output_plan",
        "description": "Return the complete meal plan as structured JSON.",
        "input_schema": schema,
    }


class _RecallLegacyCheckpoint(Exception):
    """Config allows a paid re-call for an E1 checkpoint with no handle map."""


# Plant diets drop eggs and dairy. Every diet keeps the two plant examples.
BREAKFAST_EXAMPLES_BY_DIET: dict[DietType, tuple[str, ...]] = {
    DietType.VEGAN: ("tofu scramble", "protein oats"),
    DietType.PLANT_BASED: ("tofu scramble", "protein oats"),
    DietType.WFPB: ("tofu scramble", "protein oats"),
    DietType.PESCATARIAN: (
        "eggs",
        "Greek yoghurt",
        "tofu scramble",
        "protein oats",
    ),
    DietType.FLEXITARIAN: (
        "eggs",
        "Greek yoghurt",
        "tofu scramble",
        "protein oats",
    ),
    DietType.OMNIVORE: (
        "eggs",
        "Greek yoghurt",
        "tofu scramble",
        "protein oats",
    ),
    DietType.NO_PORK: (
        "eggs",
        "Greek yoghurt",
        "tofu scramble",
        "protein oats",
    ),
}


def breakfast_protein_rule(diet_type: DietType) -> str:
    examples = " / ".join(BREAKFAST_EXAMPLES_BY_DIET[diet_type])
    return (
        "Breakfast should still be protein-rich, using dishes allowed by the "
        f"plan's diet_type. For example: {examples}."
    )


def plan_system_prompt(duration_days: int, diet_type: DietType) -> str:
    """System prompt for one plan job. Its text is the prompt version."""
    breakfast_rule = breakfast_protein_rule(diet_type)
    return (
        f"You are Nouri's meal-plan generation engine. Given a user's profile, "
        f"macro targets, and a candidate recipe pool, produce a complete "
        f"{duration_days}-day meal plan by calling the output_plan "
        "tool exactly once.\n\n"
        "Hard constraints — never violate these:\n"
        "- Never include an ingredient listed in exclusions.\n"
        "- Every item's slot_type must be one of: breakfast, lunch, dinner, snack, "
        "juice, smoothie, extra_morning, extra_afternoon, extra_evening.\n"
        "- recipe_id must be a ref (R1..Rn) from saved_recipe_candidates or "
        "'generate_new'. Every \"generate_new\" item must have a matching entry "
        "(same title) in generated_recipes.\n"
        "- Fill every slot in plan_skeleton exactly; pinned slots are fixed; "
        "juice slots take juice recipes, smoothie slots smoothie recipes.\n"
        "- Never repeat a juice or smoothie within the same day. Reuse the same "
        "juices across different days of the week to limit food waste. Ideally "
        "one green juice per day; the day's other juice slots are energy or "
        "calming juices.\n"
        "- The same dish (same ref or same generated title) never appears twice "
        "on the same day.\n"
        "- Leftovers may repeat on non-consecutive days; components may be "
        "reused in a different preparation.\n"
        "- Breakfast slots take only breakfast dishes: a saved candidate whose "
        "meal_roles include breakfast, or a generated recipe with slot_type "
        "'breakfast'. Lunch and dinner dishes are interchangeable.\n"
        "- diet_type is this plan's chosen diet. Never use an ingredient it "
        "forbids; treat it like an exclusion.\n\n"
        "Aim each day within ±10% of its calorie target (and protein target "
        "when set). Soft targets (exact daily calories, raw %, variety) "
        "become review notes if imperfect — do not leave slots empty.\n\n"
        "Compactness is mandatory — oversized output gets truncated and fails:\n"
        "- Prefer a small unique generated_recipes pool (about 6–10 recipes).\n"
        "- Each generated recipe: ≤6 ingredients, ≤3 short steps.\n"
        "- Breakfast is lighter; lunch and dinner carry most of the day's calories.\n"
        f"- {breakfast_rule}\n"
        "- Every generated_recipes entry MUST include nutrition_per_serving "
        "(calories_kcal, protein_g, fat_g, carbohydrates_g, fiber_g) and "
        "primary_protein when there is a clear protein source.\n\n"
        "sourcing_policy governs how much you lean on saved_recipe_candidates vs "
        "generate_new:\n"
        "- prefer_saved: use a saved candidate whenever one reasonably fits the "
        "slot; only generate_new when nothing in the pool fits.\n"
        "- balanced: mix freely based on what best serves variety and the day's "
        "targets.\n"
        "- prefer_new: default to generate_new unless a saved candidate is a "
        "clearly better fit.\n\n"
        "hard_slot_assignments are user-specified and must be honored exactly as "
        "given. soft_notes_context is user color/preference — follow it where it "
        "doesn't conflict with the hard constraints above.\n\n"
        "Match diet_type and prep_type to the request context.\n\n"
        "Call output_plan once you have the full plan. Do not include commentary "
        "outside the tool call."
    )


def _format_shortfall(amount: float) -> str:
    rounded = round(amount)
    if abs(amount - rounded) < 0.05:
        return str(rounded)
    return f"{amount:.1f}"


def days_beyond_calorie_tolerance(
    plan: GeneratedPlanData,
    calorie_target: float | None,
    saved_calories: Mapping[UUID, float] | None = None,
) -> list[tuple[int, str]]:
    """Days more than 20% from calorie_target.

    Each entry is (day_number, percent_text) for "Day N is X% off target".
    Days with no target, and days whose calories cannot be resolved, are skipped.
    """
    if calorie_target is None or calorie_target <= 0:
        return []
    lookup = saved_calories or {}
    generated_by_title = {
        normalize_title(recipe.title): recipe
        for recipe in plan.generated_recipes
        if recipe.title
    }
    generated_by_id = {
        recipe.assigned_id: recipe
        for recipe in plan.generated_recipes
        if recipe.assigned_id is not None
    }
    off: list[tuple[int, str]] = []
    for day in plan.days:
        actual = _day_calories(day.items, generated_by_title, generated_by_id, lookup)
        if actual is None:
            continue
        pct = abs(actual - calorie_target) / calorie_target * 100
        if pct > 20:
            off.append((day.day_number, _format_percent_off(pct)))
    return off


def calorie_off_target_notes(day_numbers: list[int]) -> list[str]:
    return [f"Day {day_number} off target" for day_number in day_numbers]


def _format_percent_off(pct: float) -> str:
    rounded = round(pct, 1)
    if abs(rounded - round(rounded)) < 0.05:
        return str(round(rounded))
    return f"{rounded:.1f}"


def _day_calories(
    items: list[GeneratedPlanItemAI],
    generated_by_title: Mapping[str, GeneratedRecipeAI],
    generated_by_id: Mapping[UUID, GeneratedRecipeAI],
    saved_calories: Mapping[UUID, float],
) -> float | None:
    total = 0.0
    for item in items:
        calories = _item_calories(
            item, generated_by_title, generated_by_id, saved_calories
        )
        if calories is None:
            return None
        total += calories
    return total


def _item_calories(
    item: GeneratedPlanItemAI,
    generated_by_title: Mapping[str, GeneratedRecipeAI],
    generated_by_id: Mapping[UUID, GeneratedRecipeAI],
    saved_calories: Mapping[UUID, float],
) -> float | None:
    if item.calories is not None:
        return float(item.calories)
    servings = max(1, int(item.servings or 1))
    if item.recipe_id == "generate_new":
        recipe = generated_by_title.get(normalize_title(item.recipe_title))
        if recipe is None:
            return None
        return float(recipe.nutrition_per_serving.calories_kcal) * servings
    if isinstance(item.recipe_id, UUID) and item.recipe_id in generated_by_id:
        recipe = generated_by_id[item.recipe_id]
        return float(recipe.nutrition_per_serving.calories_kcal) * servings
    if isinstance(item.recipe_id, UUID) and item.recipe_id in saved_calories:
        return float(saved_calories[item.recipe_id]) * servings
    return None


def _per_serving_for_item(
    item: GeneratedPlanItemAI,
    generated_by_id: Mapping[UUID, GeneratedRecipeAI],
    snapshots: Mapping[UUID, Any],
) -> tuple[float, float, float, float, float] | None:
    recipe_id = item.recipe_id
    if isinstance(recipe_id, UUID) and recipe_id in generated_by_id:
        nutrition = generated_by_id[recipe_id].nutrition_per_serving
        return (
            float(nutrition.calories_kcal),
            float(nutrition.protein_g),
            float(nutrition.fat_g),
            float(nutrition.carbohydrates_g),
            float(nutrition.fiber_g),
        )
    if isinstance(recipe_id, UUID) and recipe_id in snapshots:
        snap = snapshots[recipe_id]
        return (
            float(snap.calories),
            float(snap.protein_g),
            float(snap.fat_g),
            float(snap.carbs_g),
            float(snap.fiber_g),
        )
    return None


def _resolved_calorie_target(job_payload: PlanGenerationJob, profile: object) -> float | None:
    raw = (
        job_payload.calorie_target
        if job_payload.calorie_target is not None
        else getattr(profile, "calorie_target", None)
    )
    if raw is None:
        return None
    value = float(raw)
    if value <= 0:
        return None
    return value


def under_target_notes(plan: GeneratedPlanData, targets: MacroTargets) -> list[str]:
    """Soft notes for days below a set calorie or protein target.

    No target (both unset) produces nothing. Carbs, fat, and fiber are ignored.
    """
    if targets.calories <= 0 and targets.protein_g <= 0:
        return []
    notes: list[str] = []
    for day in plan.days:
        if targets.calories > 0:
            actual = sum(float(item.calories or 0.0) for item in day.items)
            if actual + 1e-6 < targets.calories:
                short = _format_shortfall(targets.calories - actual)
                notes.append(
                    f"Day {day.day_number} under target: kcal short by {short}"
                )
        if targets.protein_g > 0:
            actual_protein = sum(float(item.protein_g or 0.0) for item in day.items)
            if actual_protein + 1e-6 < targets.protein_g:
                short = _format_shortfall(targets.protein_g - actual_protein)
                notes.append(
                    f"Day {day.day_number} under target: protein short by {short}"
                )
    return notes


def _role_names(meal_roles: object) -> list[str]:
    if not isinstance(meal_roles, list | tuple):
        return []
    names: list[str] = []
    for role in meal_roles:
        names.append(role.value if hasattr(role, "value") else str(role))
    return names


class PlanGeneratorAgent:
    def __init__(
        self,
        client: AnthropicClient | None = None,
        notes_preprocessor: NotesPreprocessor | None = None,
        recipe_search: RecipeSearchService | None = None,
        plan_validator: PlanValidator | None = None,
        slot_assigner: SlotAssigner | None = None,
        nutrition_validator: NutritionValidator | None = None,
    ) -> None:
        self._client = client or AnthropicClient()
        self._notes = notes_preprocessor or NotesPreprocessor()
        self._search = recipe_search or RecipeSearchService()
        self._validator = plan_validator or PlanValidator()
        self._assigner = slot_assigner or SlotAssigner(plan_validator=self._validator)
        self._nutrition = nutrition_validator or NutritionValidator()
        self.dish_flags: list[str] = []

    async def generate(
        self,
        job_payload: PlanGenerationJob,
        db: AsyncSession,
        *,
        on_progress: PlanProgressFn | None = None,
        saved_llm_output: dict[str, Any] | None = None,
        on_llm_output: LlmOutputFn | None = None,
        on_model_call_start: ModelStartFn | None = None,
        deadline: float | None = None,
        job_id: UUID | None = None,
    ) -> GeneratedPlanData:
        profile = await ProfileService().get_profile(job_payload.user_id, db)
        days_total = job_payload.duration_days
        await _emit_progress(on_progress, 10, "finding_recipes", 0, days_total)
        exclusions_rows = await ProfileService().get_exclusions(
            job_payload.user_id, db
        )
        # TODO: ExclusionView is built without aliases, so alias containment
        # cannot see canonical aliases until this view is populated.
        exclusion_views = tuple(
            ExclusionView(
                raw_name=e.ingredient_name_raw or "",
                ingredient_id=e.ingredient_id,
            )
            for e in exclusions_rows
        )

        notes_result = self._notes.extract(
            job_payload.notes or "",
            await self._load_recipe_titles(job_payload.user_id, db),
            duration_days=job_payload.duration_days,
        )
        hard_slot_assignments, soft_notes_context = self._unpack_notes(notes_result)
        pins, pinned = await self._load_pins(
            hard_slot_assignments, job_payload.user_id, db
        )
        self._assert_pins_allowed(pins, pinned, exclusion_views)
        juice_configs = await self._load_juice_configs(job_payload.plan_id, db)
        try:
            skeleton = build_skeleton(
                duration_days=job_payload.duration_days,
                juicing_enabled=bool(job_payload.include_juicing),
                juice_configs=juice_configs,
                pins=pins,
            )
        except SkeletonError as exc:
            raise PlanGenerationFailedError(str(exc)) from exc

        excluded_ids = await ExclusionService().matching_ingredient_ids(
            exclusions_rows, db
        )
        pinned_slots = self._layout_pins(skeleton)
        calorie_target = _resolved_calorie_target(job_payload, profile)
        candidates: list[object] = []
        layout_warnings: list[str] = []
        resumed = False
        self.dish_flags = []

        plan_data: GeneratedPlanData | None
        if saved_llm_output is not None:
            try:
                plan_data = self._plan_from_checkpoint(saved_llm_output)
            except _RecallLegacyCheckpoint:
                plan_data = None
            if plan_data is not None:
                resumed = True
                (
                    resume_roles,
                    resume_titles,
                    resume_types,
                ) = await self._resume_layout_maps(
                    saved_llm_output, job_payload.user_id, db
                )
                self._raise_generated_dish_flags(plan_data, resume=True)
                _, layout_warnings = self._check_layout(
                    plan_data,
                    resume_roles,
                    resume_titles,
                    pinned_slots,
                    resume=True,
                    candidate_types=resume_types,
                    skeleton=skeleton,
                )
        else:
            plan_data = None
        if plan_data is None:
            candidates = await self._search.planning_candidates(
                job_payload.user_id,
                job_payload.diet_type.value,
                ("breakfast", "lunch", "dinner"),
                excluded_ids,
                db,
                juicing_enabled=bool(job_payload.include_juicing),
            )
            handles = self._build_handles(candidates, pins)
            (
                candidate_roles,
                candidate_titles,
                candidate_types,
            ) = await self._fresh_layout_maps(
                candidates, pinned, job_payload.user_id, db
            )
            candidate_summaries = self._summarise_candidates(candidates, handles)
            await _emit_progress(on_progress, 25, "generating_week", 0, days_total)

            context_block = {
                "user_profile": {
                    "diet_type": job_payload.diet_type.value,
                    "cooking_type": (
                        job_payload.cooking_type or profile.cooking_type
                    ).value,
                    "calorie_target": job_payload.calorie_target
                    or profile.calorie_target,
                    "protein_g_target": str(
                        job_payload.protein_g_target or profile.protein_g_target
                    ),
                    "carbs_g_target": str(
                        job_payload.carbs_g_target or profile.carbs_g_target
                    ),
                    "fat_g_target": str(
                        job_payload.fat_g_target or profile.fat_g_target
                    ),
                    "fiber_g_target": str(
                        job_payload.fiber_g_target or profile.fiber_g_target
                    ),
                    "sourcing_policy": job_payload.sourcing_policy.value,
                    "include_juicing": job_payload.include_juicing,
                },
                "exclusions": [e.raw_name for e in exclusion_views],
                "saved_recipe_candidates": candidate_summaries,
                "plan_skeleton": skeleton.to_prompt(
                    {recipe_id: ref for ref, recipe_id in handles.items()}
                ),
                "hard_slot_assignments": hard_slot_assignments,
                "soft_notes_context": soft_notes_context,
                "duration_days": job_payload.duration_days,
            }

            system_prompt = plan_system_prompt(
                job_payload.duration_days, job_payload.diet_type
            )
            user_prompt = (
                f"Generate a {job_payload.duration_days}-day meal plan from the context "
                "below. Use saved_recipe_candidates where sourcing_policy favors it; "
                "otherwise propose new recipes via generate_new. Respect "
                "hard_slot_assignments exactly and follow soft_notes_context where it "
                "doesn't conflict with the hard constraints in the system prompt.\n"
                f"<generation_context>{json.dumps(context_block, default=str)}</generation_context>"
            )
            if on_model_call_start is not None:
                await on_model_call_start()
            plan_data, layout_warnings, generated_flags = await self._call_and_parse(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                trace_id=job_payload.trace_id,
                deadline=deadline,
                user_id=job_payload.user_id,
                job_id=job_id,
                handles=handles,
                candidate_roles=candidate_roles,
                candidate_titles=candidate_titles,
                candidate_types=candidate_types,
                pinned_slots=pinned_slots,
                skeleton=skeleton,
                calorie_target=calorie_target,
                saved_calories=self._saved_calories(candidates, pinned),
            )
            self._remember_dish_flags(generated_flags)
            if on_llm_output is not None:
                await on_llm_output(
                    {
                        "output": plan_data.model_dump(mode="json"),
                        "handles": {
                            ref: str(recipe_id) for ref, recipe_id in handles.items()
                        },
                        "roles": {
                            str(recipe_id): list(candidate_roles.get(recipe_id, []))
                            for recipe_id in handles.values()
                        },
                        "titles": {
                            str(recipe_id): candidate_titles.get(recipe_id, "")
                            for recipe_id in handles.values()
                        },
                        "types": {
                            str(recipe_id): candidate_types.get(recipe_id, "")
                            for recipe_id in handles.values()
                        },
                    }
                )
        await _emit_progress(on_progress, 55, "assigning_slots", 0, days_total)
        plan_data = self._assign_generated_recipe_ids(plan_data)
        plan_data = self._apply_skeleton(plan_data, skeleton, pinned, strict=True)
        self._check_generated_nutrition(plan_data)

        cooking = job_payload.cooking_type or profile.cooking_type
        targets = MacroTargets(
            calories=float(
                job_payload.calorie_target
                if job_payload.calorie_target is not None
                else (profile.calorie_target or 0)
            ),
            protein_g=float(
                job_payload.protein_g_target
                if job_payload.protein_g_target is not None
                else (profile.protein_g_target or 0)
            ),
            carbs_g=float(
                job_payload.carbs_g_target
                if job_payload.carbs_g_target is not None
                else (profile.carbs_g_target or 0)
            ),
            fat_g=float(
                job_payload.fat_g_target
                if job_payload.fat_g_target is not None
                else (profile.fat_g_target or 0)
            ),
            fiber_g=float(
                job_payload.fiber_g_target
                if job_payload.fiber_g_target is not None
                else (profile.fiber_g_target or Decimal(0))
            ),
        )
        user_view = UserProfileView(
            cooking_type=cooking.value,
            exclusions=exclusion_views,
        )

        saved_ids = self._saved_recipe_ids(plan_data)
        saved_ids.extend(c.recipe_id for c in candidates if isinstance(c, RecipeCandidate))
        snapshots = await RecipeService().load_plan_snapshots(
            job_payload.user_id, saved_ids, db
        )
        pool = self._build_pool(plan_data, snapshots)

        # Primary path: trust the model's slot layout. Deterministic checkers advise;
        # they do not veto a usable week (exclusions + hard pins remain hard).
        plan_data = self._materialize_llm_plan(plan_data, snapshots)
        self._remember_dish_flags(
            self._saved_dish_flags(plan_data, snapshots)
            + self._day_total_flags(plan_data, snapshots)
        )
        if self.dish_flags:
            logger.info(
                "dish_flags",
                flags=list(self.dish_flags),
                trace_id=job_payload.trace_id,
            )
        soft_warnings: list[str] = []
        soft_warnings.extend(layout_warnings)
        if resumed:
            resumed_off = [
                day_number
                for day_number, _pct in days_beyond_calorie_tolerance(
                    plan_data, calorie_target
                )
            ]
            for note in calorie_off_target_notes(resumed_off):
                if note not in soft_warnings:
                    soft_warnings.append(note)

        if settings.plan_assigner_polish:
            policy = job_payload.sourcing_policy.value
            if policy not in ("prefer_saved", "balanced", "prefer_new"):
                policy = "balanced"
            slots = self._slot_specs(skeleton)
            assignment = self._assigner.assign(
                slots,
                pool,
                targets,
                cooking.value,
                exclusion_views,
                sourcing_policy=policy,
            )
            if assignment.feasible and assignment.days:
                polished = self._apply_skeleton(
                    self._apply_assignment(plan_data, assignment),
                    skeleton,
                    pinned,
                    strict=False,
                )
                if self._avg_day_calories(polished) >= self._avg_day_calories(plan_data):
                    plan_data = polished
                else:
                    soft_warnings.append(
                        "Kept the model’s meal layout; assigner polish did not improve "
                        "average daily calories."
                    )
                soft_warnings.extend(assignment.warnings)
            elif assignment.errors:
                soft_warnings.append(
                    "Assigner could not improve the plan: "
                    + "; ".join(assignment.errors[:3])
                )
        else:
            soft_warnings.extend(under_target_notes(plan_data, targets))

        missing_pins = self._missing_hard_pins_from_plan(
            plan_data, hard_slot_assignments
        )
        if missing_pins:
            raise PlanGenerationFailedError(
                "Hard slot assignments not satisfied: " + "; ".join(missing_pins)
            )

        await _emit_progress(on_progress, 70, "saving", 0, days_total)
        draft_view = self._to_plan_draft_view(plan_data, snapshots, pinned)
        result = self._validator.validate(draft_view, user_view, targets)
        hard = [e for e in result.errors if "excluded ingredient" in e.lower()]
        if hard:
            logger.error(
                "plan_validation_failure",
                plan_id=str(job_payload.plan_id),
                errors=list(result.errors),
                trace_id=job_payload.trace_id,
            )
            raise PlanGenerationFailedError(
                "Plan failed validation: " + "; ".join(hard)
            )
        if not result.passed:
            logger.warning(
                "plan_validation_soft_accept",
                plan_id=str(job_payload.plan_id),
                warnings=list(result.errors),
                trace_id=job_payload.trace_id,
            )
            soft_warnings.extend(result.errors)

        for note in reversed(consecutive_main_dish_notes(plan_data)):
            if note not in soft_warnings:
                soft_warnings.insert(0, note)

        review_notes = self._build_review_notes(soft_warnings, ())
        if review_notes:
            plan_data = plan_data.model_copy(update={"review_notes": review_notes})

        logger.info(
            "plan_generation_validated",
            plan_id=str(job_payload.plan_id),
            days=len(plan_data.days),
            pool_size=len(pool),
            soft_warnings=len(soft_warnings),
            trace_id=job_payload.trace_id,
        )
        return plan_data

    @staticmethod
    def _build_review_notes(
        assignment_warnings: tuple[str, ...] | list[str],
        validation_errors: tuple[str, ...] | list[str],
    ) -> str | None:
        notes = []
        for msg in [*assignment_warnings, *validation_errors]:
            text = msg.strip()
            if text and text not in notes:
                notes.append(text)
        if not notes:
            return None
        bullets = "\n".join(f"- {n}" for n in notes[:12])
        return (
            "This plan was saved with tradeoffs so you still have meals to review:\n"
            f"{bullets}\n\n"
            "We prioritized a usable week over perfect macros/variety. "
            "Swap individual meals anytime, or regenerate with denser recipes / "
            "clearer macro targets on your profile."
        )

    async def _call_and_parse(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        trace_id: str | None,
        deadline: float | None = None,
        user_id: UUID | None = None,
        job_id: UUID | None = None,
        handles: dict[str, UUID] | None = None,
        candidate_roles: Mapping[UUID, list[str]] | None = None,
        candidate_titles: Mapping[UUID, str] | None = None,
        candidate_types: Mapping[UUID, str] | None = None,
        pinned_slots: set[PinnedSlot] | None = None,
        skeleton: PlanSkeleton | None = None,
        calorie_target: float | None = None,
        saved_calories: Mapping[UUID, float] | None = None,
    ) -> tuple[GeneratedPlanData, list[str], list[str]]:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_prompt}
        ]
        tool = _plan_tool(handles or {})
        model = route_model(AgentTask.PLAN_GENERATION)
        # Compact 7-day plans still need headroom; truncation must retry cleanly.
        max_tokens = 16384
        last_error: Exception | None = None
        pending_soft: list[str] = []

        for parse_attempt in range(2):
            if parse_attempt > 0 and not attempt_fits(deadline):
                raise PlanGenerationFailedError(
                    f"Failed to parse plan output: {last_error}"
                ) from last_error
            message = await self._client.complete(
                messages,
                model=model,
                tools=[tool],
                tool_choice={"type": "tool", "name": "output_plan"},
                max_tokens=max_tokens,
                system=system_prompt,
                trace_id=trace_id,
                deadline=deadline,
                user_id=user_id,
                job_id=job_id,
                task=AgentTask.PLAN_GENERATION.value,
            )
            try:
                if getattr(message, "stop_reason", None) == "max_tokens":
                    raise ValueError(
                        "output_plan was truncated at max_tokens; return a complete "
                        "plan with a smaller generated_recipes pool, ≤6 ingredients "
                        "and ≤3 short steps each, and full nutrition_per_serving"
                    )
                plan = self._extract_plan(message, handles or {})
                self._assert_pool_nutrition(plan)
                pending_soft, hard_flags = self._split_generated_dish_flags(plan)
                if hard_flags:
                    raise ValueError("; ".join(hard_flags))
                _errors, warnings = self._check_layout(
                    plan,
                    candidate_roles or {},
                    candidate_titles or {},
                    pinned_slots or set(),
                    resume=False,
                    candidate_types=candidate_types or {},
                    skeleton=skeleton,
                )
                off_target = days_beyond_calorie_tolerance(
                    plan, calorie_target, saved_calories
                )
                if off_target and parse_attempt == 0:
                    detail = "; ".join(
                        f"Day {day_number} is {pct}% off target"
                        for day_number, pct in off_target
                    )
                    raise ValueError(detail)
                if off_target:
                    warnings.extend(
                        calorie_off_target_notes(
                            [day_number for day_number, _pct in off_target]
                        )
                    )
                return plan, warnings, pending_soft
            except Exception as exc:
                last_error = exc
                if parse_attempt >= 1:
                    self._remember_dish_flags(pending_soft)
                    raise PlanGenerationFailedError(
                        f"Failed to parse plan output: {exc}"
                    ) from exc
                messages = self._retry_messages_after_failure(
                    user_prompt=user_prompt,
                    message=message,
                    error=exc,
                )
        raise PlanGenerationFailedError(
            f"Failed to parse plan output: {last_error}"
        )

    @staticmethod
    def _retry_messages_after_failure(
        *,
        user_prompt: str,
        message: Any,
        error: Exception,
    ) -> list[dict[str, Any]]:
        """Build a valid Anthropic retry transcript after a failed output_plan.

        Truncated tool_use JSON cannot be safely continued — restart compact.
        Complete tool_use failures must be closed with tool_result blocks.
        """
        if getattr(message, "stop_reason", None) == "max_tokens":
            return [
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\nCRITICAL: Previous output_plan was "
                        f"truncated ({error}). Call output_plan once with a COMPLETE "
                        "plan. Use ~6–10 unique generated_recipes. Each recipe: "
                        "≤6 ingredients, ≤3 short steps, "
                        "and required nutrition_per_serving."
                    ),
                }
            ]

        tool_results: list[dict[str, Any]] = []
        for block in getattr(message, "content", []) or []:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_use_id = getattr(block, "id", None)
            if not isinstance(tool_use_id, str) or not tool_use_id:
                continue
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "is_error": True,
                    "content": (
                        f"{error}. Call output_plan again with a complete valid "
                        "plan. Every generate_new item needs matching "
                        "generated_recipes with nutrition_per_serving."
                    ),
                }
            )
        if not tool_results:
            return [
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\nPrevious output failed: {error}. "
                        "Call output_plan with a complete valid plan."
                    ),
                }
            ]
        return [
            {"role": "assistant", "content": message.content},
            {"role": "user", "content": tool_results},
        ]

    def _extract_plan(
        self, message: Any, handles: Mapping[str, UUID]
    ) -> GeneratedPlanData:
        for block in message.content:
            if block.type == "tool_use" and block.name == "output_plan":
                raw = block.input if isinstance(block.input, dict) else {}
                resolved = self._resolve_recipe_refs(
                    copy.deepcopy(raw), handles, from_checkpoint=False
                )
                return GeneratedPlanData.model_validate(resolved)
        raise ValueError("Model did not call output_plan")

    def _plan_from_checkpoint(self, saved: dict[str, Any]) -> GeneratedPlanData:
        output = saved.get("output")
        raw_handles = saved.get("handles")
        if isinstance(output, dict) and isinstance(raw_handles, dict):
            handles = {
                str(key): value if isinstance(value, UUID) else UUID(str(value))
                for key, value in raw_handles.items()
            }
            try:
                resolved = self._resolve_recipe_refs(
                    copy.deepcopy(output), handles, from_checkpoint=True
                )
                return GeneratedPlanData.model_validate(resolved)
            except PlanGenerationFailedError:
                raise
            except Exception as exc:
                raise PlanGenerationFailedError(
                    f"Saved plan output could not be resumed: {exc}"
                ) from exc
        if settings.plan_resume_legacy_checkpoint == "recall":
            raise _RecallLegacyCheckpoint()
        raise PlanGenerationFailedError(
            "Saved plan output has no handle map and will not be resumed. "
            "plan_resume_legacy_checkpoint=recall pays for a new model call."
        )

    @staticmethod
    def _resolve_recipe_refs(
        data: dict[str, Any],
        handles: Mapping[str, UUID],
        *,
        from_checkpoint: bool,
    ) -> dict[str, Any]:
        allowed_ids = {str(value) for value in handles.values()}
        for day in data.get("days") or []:
            if not isinstance(day, dict):
                continue
            for item in day.get("items") or []:
                if not isinstance(item, dict):
                    continue
                recipe_id = item.get("recipe_id")
                if recipe_id is None or recipe_id == "generate_new":
                    continue
                if not from_checkpoint:
                    if isinstance(recipe_id, str) and recipe_id in handles:
                        item["recipe_id"] = str(handles[recipe_id])
                        continue
                    raise ValueError(f"Unknown recipe ref: {recipe_id}")
                text = str(recipe_id)
                if text in allowed_ids:
                    item["recipe_id"] = text
                    continue
                raise PlanGenerationFailedError(
                    f"Saved plan output has an unmapped recipe id: {recipe_id}"
                )
        return data

    @staticmethod
    def _assert_pool_nutrition(plan: GeneratedPlanData) -> None:
        """Reject plans whose generated recipes cannot feed SlotAssigner."""
        unknown_ids = _nutrition_unknown_ids(plan)
        missing = [
            recipe.title
            for recipe in plan.generated_recipes
            if recipe.assigned_id not in unknown_ids
            and (
                recipe.nutrition_per_serving is None
                or recipe.nutrition_per_serving.calories_kcal <= 0
            )
        ]
        if missing:
            raise ValueError(
                "generated_recipes missing usable nutrition_per_serving for: "
                + ", ".join(missing[:8])
            )

    def _assign_generated_recipe_ids(
        self, plan: GeneratedPlanData
    ) -> GeneratedPlanData:
        """Match generate_new slots to generated_recipes by title; assign UUIDs."""
        by_title: dict[str, GeneratedRecipeAI] = {}
        updated_recipes: list[GeneratedRecipeAI] = []
        for recipe in plan.generated_recipes:
            assigned = recipe.assigned_id or uuid.uuid4()
            updated = recipe.model_copy(update={"assigned_id": assigned})
            updated_recipes.append(updated)
            by_title[updated.title.strip().lower()] = updated

        new_days = []
        for day in plan.days:
            new_items = []
            for item in day.items:
                if item.recipe_id == "generate_new":
                    match = by_title.get(item.recipe_title.strip().lower())
                    if match and match.assigned_id is not None:
                        new_items.append(
                            item.model_copy(update={"recipe_id": match.assigned_id})
                        )
                    else:
                        new_items.append(item)
                else:
                    new_items.append(item)
            new_days.append(day.model_copy(update={"items": new_items}))

        return GeneratedPlanData(days=new_days, generated_recipes=updated_recipes)

    def _check_generated_nutrition(self, plan: GeneratedPlanData) -> None:
        unknown_ids = _nutrition_unknown_ids(plan)
        for recipe in plan.generated_recipes:
            if recipe.assigned_id in unknown_ids:
                continue
            n = recipe.nutrition_per_serving
            try:
                self._nutrition.check(
                    NutritionPerServing(
                        calories_kcal=n.calories_kcal,
                        protein_g=n.protein_g,
                        fat_g=n.fat_g,
                        carbohydrates_g=n.carbohydrates_g,
                        fiber_g=n.fiber_g,
                    )
                )
            except NutritionOutOfRangeError:
                logger.warning(
                    "generated_recipe_nutrition_out_of_range",
                    title=recipe.title,
                )

    def _remember_dish_flags(self, flags: list[str]) -> None:
        for flag in flags:
            if flag not in self.dish_flags:
                self.dish_flags.append(flag)

    def _raise_generated_dish_flags(
        self, plan: GeneratedPlanData, *, resume: bool
    ) -> None:
        soft, hard = self._split_generated_dish_flags(plan)
        self._remember_dish_flags(soft)
        if not hard:
            return
        message = "; ".join(hard)
        if resume:
            raise PlanGenerationFailedError(message)
        raise ValueError(message)

    def _split_generated_dish_flags(
        self, plan: GeneratedPlanData
    ) -> tuple[list[str], list[str]]:
        soft: list[str] = []
        hard: list[str] = []
        for recipe in plan.generated_recipes:
            dish = self._dish_from_recipe(plan, recipe)
            soft.extend(
                flag
                for flag in check_dish_nutrition(dish)
                if flag not in hard_dish_flags(dish)
            )
            hard.extend(hard_dish_flags(dish))
        return soft, hard

    def _saved_dish_flags(
        self, plan: GeneratedPlanData, snapshots: Mapping[UUID, Any]
    ) -> list[str]:
        generated_ids = {
            recipe.assigned_id
            for recipe in plan.generated_recipes
            if recipe.assigned_id is not None
        }
        flags: list[str] = []
        for day in plan.days:
            for item in day.items:
                recipe_id = item.recipe_id
                if not isinstance(recipe_id, UUID) or recipe_id in generated_ids:
                    continue
                snap = snapshots.get(recipe_id)
                if snap is None:
                    continue
                dish = DishNutrition(
                    name=str(getattr(snap, "title", item.recipe_title)),
                    path=f"day{day.day_number}.{item.slot_type}",
                    calories_kcal=float(snap.calories),
                    protein_g=float(snap.protein_g),
                    fat_g=float(snap.fat_g),
                    carbohydrates_g=float(snap.carbs_g),
                    fiber_g=float(snap.fiber_g),
                    ingredient_grams=None,
                )
                flags.extend(check_dish_nutrition(dish))
        return flags

    def _day_total_flags(
        self, plan: GeneratedPlanData, snapshots: Mapping[UUID, Any]
    ) -> list[str]:
        by_id = {
            recipe.assigned_id: recipe
            for recipe in plan.generated_recipes
            if recipe.assigned_id is not None
        }
        flags: list[str] = []
        for day in plan.days:
            servings_rows: list[ServingNutrition] = []
            declared_calories = declared_protein = declared_fat = 0.0
            declared_carbs = declared_fiber = 0.0
            complete = True
            for item in day.items:
                per = _per_serving_for_item(item, by_id, snapshots)
                if per is None or item.nutrition_unknown or item.calories is None:
                    complete = False
                    break
                calories, protein, fat, carbs, fiber = per
                servings = max(1, int(item.servings or 1))
                servings_rows.append(
                    ServingNutrition(
                        servings=servings,
                        calories_kcal=calories,
                        protein_g=protein,
                        fat_g=fat,
                        carbohydrates_g=carbs,
                        fiber_g=fiber,
                    )
                )
                declared_calories += float(item.calories)
                declared_protein += float(item.protein_g or 0)
                declared_fat += float(item.fat_g or 0)
                declared_carbs += float(item.carbs_g or 0)
                declared_fiber += float(item.fiber_g or 0)
            if complete and servings_rows:
                flags.extend(
                    check_day_totals(
                        day.day_number,
                        servings_rows,
                        DayTotals(
                            calories_kcal=declared_calories,
                            protein_g=declared_protein,
                            fat_g=declared_fat,
                            carbohydrates_g=declared_carbs,
                            fiber_g=declared_fiber,
                        ),
                    )
                )
        return flags

    @staticmethod
    def _dish_from_recipe(
        plan: GeneratedPlanData, recipe: GeneratedRecipeAI
    ) -> DishNutrition:
        path = recipe.title
        title_key = normalize_title(recipe.title)
        for day in plan.days:
            for item in day.items:
                if normalize_title(item.recipe_title) == title_key:
                    path = f"day{day.day_number}.{item.slot_type}"
                    break
            else:
                continue
            break
        nutrition = recipe.nutrition_per_serving
        return DishNutrition(
            name=recipe.title,
            path=path,
            calories_kcal=float(nutrition.calories_kcal),
            protein_g=float(nutrition.protein_g),
            fat_g=float(nutrition.fat_g),
            carbohydrates_g=float(nutrition.carbohydrates_g),
            fiber_g=float(nutrition.fiber_g),
            ingredient_grams=grams_from_ingredients(recipe.ingredients),
        )

    def _saved_recipe_ids(self, plan: GeneratedPlanData) -> list[UUID]:
        generated = {
            r.assigned_id for r in plan.generated_recipes if r.assigned_id is not None
        }
        ids: list[UUID] = []
        for day in plan.days:
            for item in day.items:
                if item.recipe_id == "generate_new":
                    continue
                rid = item.recipe_id
                if isinstance(rid, UUID) and rid not in generated:
                    ids.append(rid)
        return ids

    def _build_pool(
        self,
        plan: GeneratedPlanData,
        snapshots: dict[UUID, Any],
    ) -> list[AssignableRecipe]:
        pool: list[AssignableRecipe] = []
        seen: set[UUID] = set()
        for snap in snapshots.values():
            if snap.recipe_id in seen:
                continue
            seen.add(snap.recipe_id)
            pool.append(
                AssignableRecipe(
                    recipe_id=snap.recipe_id,
                    title=snap.title,
                    calories=snap.calories,
                    protein_g=snap.protein_g,
                    carbs_g=snap.carbs_g,
                    fat_g=snap.fat_g,
                    fiber_g=snap.fiber_g,
                    prep_method=(
                        snap.prep_method.value
                        if snap.prep_method is not None
                        else None
                    ),
                    primary_protein=snap.primary_protein,
                    ingredients=tuple(
                        RecipeIngredientView(
                            name=ing.name, ingredient_id=ing.ingredient_id
                        )
                        for ing in snap.ingredients
                    ),
                    slot_hint=snap.slot_hint,
                    is_saved=True,
                )
            )
        for recipe in plan.generated_recipes:
            if recipe.assigned_id is None:
                continue
            if recipe.assigned_id in seen:
                continue
            seen.add(recipe.assigned_id)
            n = recipe.nutrition_per_serving
            primary = (
                recipe.primary_protein.value
                if recipe.primary_protein is not None
                else None
            )
            pool.append(
                AssignableRecipe(
                    recipe_id=recipe.assigned_id,
                    title=recipe.title,
                    calories=n.calories_kcal,
                    protein_g=n.protein_g,
                    carbs_g=n.carbohydrates_g,
                    fat_g=n.fat_g,
                    fiber_g=n.fiber_g,
                    prep_method=recipe.prep_type.value,
                    primary_protein=primary,
                    ingredients=tuple(
                        RecipeIngredientView(
                            name=ing.ingredient_name,
                            ingredient_id=ing.ingredient_id,
                        )
                        for ing in recipe.ingredients
                    ),
                    slot_hint=recipe.slot_type,
                    is_saved=False,
                )
            )
        return pool

    @staticmethod
    def _slot_specs(skeleton: PlanSkeleton) -> list[SlotSpec]:
        return [
            SlotSpec(
                day_number=slot.day_number,
                slot=slot.slot,
                pinned_recipe_id=slot.pinned_recipe_id,
            )
            for slot in skeleton.slots
        ]

    def _missing_hard_pins(
        self, days: tuple[PlanDayView, ...], hard_assignments: list[Any]
    ) -> list[str]:
        placed: set[tuple[int, str, UUID]] = set()
        for day in days:
            for item in day.items:
                if item.recipe_id is None:
                    continue
                placed.add((day.day_number, item.slot, item.recipe_id))
        missing: list[str] = []
        for item in hard_assignments:
            if hasattr(item, "day"):
                day_n, slot, rid = int(item.day), str(item.slot_type), item.recipe_id
            elif isinstance(item, dict) and item.get("recipe_id"):
                day_n = int(item["day"])
                slot = str(item["slot_type"])
                rid = UUID(str(item["recipe_id"]))
            else:
                continue
            if (day_n, slot, rid) not in placed:
                missing.append(f"day {day_n} {slot} → {rid}")
        return missing

    def _missing_hard_pins_from_plan(
        self, plan: GeneratedPlanData, hard_assignments: list[Any]
    ) -> list[str]:
        placed: set[tuple[int, str, UUID]] = set()
        for day in plan.days:
            for item in day.items:
                if isinstance(item.recipe_id, UUID):
                    placed.add((day.day_number, item.slot_type, item.recipe_id))
        missing: list[str] = []
        for item in hard_assignments:
            if hasattr(item, "day"):
                day_n, slot, rid = int(item.day), str(item.slot_type), item.recipe_id
            elif isinstance(item, dict) and item.get("recipe_id"):
                day_n = int(item["day"])
                slot = str(item["slot_type"])
                rid = UUID(str(item["recipe_id"]))
            else:
                continue
            if (day_n, slot, rid) not in placed:
                missing.append(f"day {day_n} {slot} → {rid}")
        return missing

    @staticmethod
    def _avg_day_calories(plan: GeneratedPlanData) -> float:
        if not plan.days:
            return 0.0
        totals = [
            sum(float(item.calories or 0.0) for item in day.items)
            for day in plan.days
        ]
        return sum(totals) / len(totals)

    def _materialize_llm_plan(
        self,
        plan: GeneratedPlanData,
        snapshots: dict[UUID, Any],
    ) -> GeneratedPlanData:
        """Stamp per-item macros from recipe nutrition onto the model's layout."""
        by_gen: dict[UUID, GeneratedRecipeAI] = {
            r.assigned_id: r
            for r in plan.generated_recipes
            if r.assigned_id is not None
        }
        new_days: list[GeneratedPlanDayAI] = []
        for day in plan.days:
            new_items: list[GeneratedPlanItemAI] = []
            for item in day.items:
                servings = max(1, int(item.servings or 1))
                if item.nutrition_unknown:
                    new_items.append(
                        item.model_copy(
                            update={
                                "servings": servings,
                                "nutrition_unknown": True,
                                "calories": None,
                                "protein_g": None,
                                "carbs_g": None,
                                "fat_g": None,
                                "fiber_g": None,
                            }
                        )
                    )
                    continue
                updates: dict[str, Any] = {"servings": servings}
                rid = item.recipe_id
                if isinstance(rid, UUID) and rid in by_gen:
                    gen = by_gen[rid]
                    n = gen.nutrition_per_serving
                    updates.update(
                        {
                            "recipe_title": gen.title,
                            "calories": n.calories_kcal * servings,
                            "protein_g": n.protein_g * servings,
                            "carbs_g": n.carbohydrates_g * servings,
                            "fat_g": n.fat_g * servings,
                            "fiber_g": n.fiber_g * servings,
                            "prep_method": gen.prep_type,
                            "primary_protein": (
                                gen.primary_protein.value
                                if gen.primary_protein is not None
                                else None
                            ),
                        }
                    )
                elif isinstance(rid, UUID) and rid in snapshots:
                    snap = snapshots[rid]
                    prep = snap.prep_method
                    if isinstance(prep, PreparationType):
                        prep_val = prep
                    elif isinstance(prep, str):
                        try:
                            prep_val = PreparationType(prep)
                        except ValueError:
                            prep_val = None
                    else:
                        prep_val = None
                    updates.update(
                        {
                            "recipe_title": snap.title,
                            "calories": float(snap.calories) * servings,
                            "protein_g": float(snap.protein_g) * servings,
                            "carbs_g": float(snap.carbs_g) * servings,
                            "fat_g": float(snap.fat_g) * servings,
                            "fiber_g": float(snap.fiber_g) * servings,
                            "prep_method": prep_val,
                            "primary_protein": snap.primary_protein,
                        }
                    )
                new_items.append(item.model_copy(update=updates))
            new_days.append(day.model_copy(update={"items": new_items}))

        placed = {
            item.recipe_id
            for day in new_days
            for item in day.items
            if isinstance(item.recipe_id, UUID)
        }
        generated = [
            recipe
            for recipe in plan.generated_recipes
            if recipe.assigned_id is not None and recipe.assigned_id in placed
        ]
        return GeneratedPlanData(
            days=new_days,
            generated_recipes=generated,
            review_notes=plan.review_notes,
        )

    def _apply_assignment(
        self, plan: GeneratedPlanData, assignment: Any
    ) -> GeneratedPlanData:
        by_id: dict[UUID, GeneratedRecipeAI] = {
            r.assigned_id: r
            for r in plan.generated_recipes
            if r.assigned_id is not None
        }
        days: list[GeneratedPlanDayAI] = []
        for day in assignment.days:
            items: list[GeneratedPlanItemAI] = []
            for item in day.items:
                rid: UUID | str = (
                    item.recipe_id if item.recipe_id is not None else "generate_new"
                )
                servings = 1
                if item.recipe_id is not None and item.recipe_id in by_id:
                    gen = by_id[item.recipe_id]
                    if gen.nutrition_per_serving and gen.nutrition_per_serving.calories_kcal:
                        base = gen.nutrition_per_serving.calories_kcal
                        if base > 0 and item.calories is not None:
                            servings = max(1, round(item.calories / base))
                prep = None
                if item.prep_method:
                    try:
                        prep = PreparationType(item.prep_method)
                    except ValueError:
                        prep = None
                items.append(
                    GeneratedPlanItemAI(
                        slot_type=item.slot,  # type: ignore[arg-type]
                        recipe_id=rid,  # type: ignore[arg-type]
                        recipe_title=item.name,
                        servings=servings,
                        calories=item.calories,
                        protein_g=item.protein_g,
                        carbs_g=item.carbs_g,
                        fat_g=item.fat_g,
                        fiber_g=item.fiber_g,
                        prep_method=prep,
                        primary_protein=item.primary_protein,
                    )
                )
            days.append(GeneratedPlanDayAI(day_number=day.day_number, items=items))
        placed = {
            item.recipe_id
            for day in days
            for item in day.items
            if isinstance(item.recipe_id, UUID)
        }
        generated = [
            recipe
            for recipe in plan.generated_recipes
            if recipe.assigned_id is not None and recipe.assigned_id in placed
        ]
        return GeneratedPlanData(days=days, generated_recipes=generated)

    def _to_plan_draft_view(
        self,
        plan: GeneratedPlanData,
        snapshots: Mapping[UUID, Any],
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
    ) -> PlanDraftView:
        recipe_ingredients: dict[UUID, tuple[RecipeIngredientView, ...]] = {}
        for gen in plan.generated_recipes:
            if gen.assigned_id is None:
                continue
            recipe_ingredients[gen.assigned_id] = tuple(
                RecipeIngredientView(
                    name=ing.ingredient_name,
                    ingredient_id=ing.ingredient_id,
                )
                for ing in gen.ingredients
            )
        for recipe_id, snap in snapshots.items():
            recipe_ingredients.setdefault(
                recipe_id,
                tuple(
                    RecipeIngredientView(
                        name=ing.name, ingredient_id=ing.ingredient_id
                    )
                    for ing in snap.ingredients
                ),
            )
        for recipe_id, snap in pinned.items():
            recipe_ingredients.setdefault(
                recipe_id,
                tuple(
                    RecipeIngredientView(
                        name=ing.name, ingredient_id=ing.ingredient_id
                    )
                    for ing in snap.ingredients
                ),
            )

        days: list[PlanDayView] = []
        for day in plan.days:
            items: list[PlanItemView] = []
            for item in day.items:
                rid: UUID | None
                if item.recipe_id == "generate_new":
                    rid = None
                else:
                    rid = item.recipe_id  # type: ignore[assignment]
                if rid is None:
                    ingredients = ()
                elif rid in recipe_ingredients:
                    ingredients = recipe_ingredients[rid]
                else:
                    raise PlanGenerationFailedError(
                        f"Saved recipe ingredients not loaded: {rid}"
                    )
                items.append(
                    PlanItemView(
                        day_number=day.day_number,
                        name=item.recipe_title,
                        slot=item.slot_type,
                        prep_method=(
                            item.prep_method.value
                            if item.prep_method is not None
                            else None
                        ),
                        calories=item.calories,
                        protein_g=item.protein_g,
                        carbs_g=item.carbs_g,
                        fat_g=item.fat_g,
                        fiber_g=item.fiber_g,
                        primary_protein=item.primary_protein,
                        recipe_id=rid,
                        ingredients=ingredients,
                        nutrition_unknown=item.nutrition_unknown,
                    )
                )
            days.append(
                PlanDayView(day_number=day.day_number, items=tuple(items))
            )
        return PlanDraftView(days=tuple(days))

    @staticmethod
    async def _load_recipe_titles(
        user_id: UUID, db: AsyncSession
    ) -> list[RecipeTitleRef]:
        result = await db.execute(
            select(Recipe.id, Recipe.name).where(
                Recipe.user_id == user_id,
                Recipe.deleted_at.is_(None),
            )
        )
        return [RecipeTitleRef(id=row.id, name=row.name) for row in result.all()]

    @staticmethod
    def _unpack_notes(notes_result: object) -> tuple[list[Any], str]:
        if notes_result is None:
            return [], ""
        if isinstance(notes_result, tuple) and len(notes_result) >= 2:
            return list(notes_result[0] or []), str(notes_result[1] or "")
        hard = getattr(notes_result, "hard_slot_assignments", None)
        soft = getattr(notes_result, "soft_notes_context", None)
        if hard is not None or soft is not None:
            serialized = []
            for item in hard or []:
                if hasattr(item, "day"):
                    serialized.append(
                        {
                            "day": item.day,
                            "slot_type": item.slot_type,
                            "recipe_id": str(item.recipe_id),
                            "recipe_name": getattr(item, "recipe_name", None),
                        }
                    )
                else:
                    serialized.append(item)
            return serialized, str(soft or "")
        return [], ""

    @staticmethod
    def _summarise_candidates(
        candidates: list[object],
        handles: Mapping[str, UUID],
    ) -> list[dict[str, Any]]:
        """Token-efficient candidate summaries. The model sees R refs, not UUIDs."""
        ref_for = {recipe_id: ref for ref, recipe_id in handles.items()}
        summaries: list[dict[str, Any]] = []
        for c in candidates:
            if isinstance(c, RecipeCandidate):
                macros = c.macro_summary
                summaries.append(
                    {
                        "ref": ref_for.get(c.recipe_id),
                        "title": c.title,
                        "diet_type": c.diet_type,
                        "cooking_type": c.cooking_type,
                        "meal_roles": list(c.meal_roles),
                        "recipe_type": c.recipe_type,
                        "calories": macros.calories,
                        "protein_g": macros.protein_g,
                        "carbs_g": macros.carbs_g,
                        "fat_g": macros.fat_g,
                    }
                )
                continue
            if isinstance(c, RecipeView):
                summaries.append({"recipe_id": str(c.id)})
                continue
            if isinstance(c, dict):
                summaries.append(
                    {
                        k: c.get(k)
                        for k in (
                            "recipe_id",
                            "id",
                            "title",
                            "name",
                            "diet_type",
                            "prep_type",
                            "calories",
                            "protein_g",
                            "carbs_g",
                            "fat_g",
                        )
                        if k in c
                    }
                )
                continue
            summaries.append({"repr": str(c)})
        return summaries

    def _check_layout(
        self,
        plan: GeneratedPlanData,
        candidate_roles: Mapping[UUID, list[str]],
        candidate_titles: Mapping[UUID, str],
        pinned_slots: set[PinnedSlot],
        *,
        resume: bool,
        candidate_types: Mapping[UUID, str] | None = None,
        skeleton: PlanSkeleton | None = None,
    ) -> tuple[list[str], list[str]]:
        result = check_layout(
            plan,
            candidate_roles=candidate_roles,
            candidate_titles=candidate_titles,
            pinned_slots=pinned_slots,
            candidate_types=candidate_types,
            skeleton=skeleton,
        )
        if result.errors:
            message = "Layout: " + "; ".join(result.errors)
            if resume:
                raise PlanGenerationFailedError(message)
            raise ValueError(message)
        return list(result.errors), list(result.warnings)

    @staticmethod
    def _layout_pins(skeleton: PlanSkeleton) -> set[PinnedSlot]:
        pins: set[PinnedSlot] = set()
        for slot in skeleton.slots:
            if slot.pinned_recipe_id is None:
                continue
            pins.add(
                (
                    slot.day_number,
                    slot.slot,
                    slot.slot_order,
                    slot.pinned_recipe_id,
                    slot.juice_time or "",
                )
            )
        return pins

    @staticmethod
    def _layout_candidate_roles(
        candidates: list[object],
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
        pin_roles: Mapping[UUID, list[str]],
    ) -> dict[UUID, list[str]]:
        roles: dict[UUID, list[str]] = {}
        for candidate in candidates:
            if isinstance(candidate, RecipeCandidate):
                roles[candidate.recipe_id] = list(candidate.meal_roles)
        for recipe_id in pinned:
            if recipe_id in roles:
                continue
            roles[recipe_id] = list(pin_roles.get(recipe_id, []))
        return roles

    @staticmethod
    def _layout_candidate_titles(
        candidates: list[object],
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
        pin_titles: Mapping[UUID, str],
    ) -> dict[UUID, str]:
        titles: dict[UUID, str] = {}
        for candidate in candidates:
            if isinstance(candidate, RecipeCandidate):
                titles[candidate.recipe_id] = candidate.title
        for recipe_id, snap in pinned.items():
            if recipe_id in titles:
                continue
            titles[recipe_id] = pin_titles.get(recipe_id) or snap.title
        return titles

    async def _fresh_layout_maps(
        self,
        candidates: list[object],
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
        user_id: UUID,
        db: AsyncSession,
    ) -> tuple[dict[UUID, list[str]], dict[UUID, str], dict[UUID, str]]:
        roles = self._layout_candidate_roles(candidates, pinned, {})
        types = self._layout_candidate_types(candidates, pinned, {})
        missing_roles = [recipe_id for recipe_id in pinned if recipe_id not in roles]
        saved_ids = self._candidate_ids(candidates, pinned)
        missing_types = [recipe_id for recipe_id in saved_ids if recipe_id not in types]
        loaded_roles: dict[UUID, list[str]] = {}
        loaded_titles: dict[UUID, str] = {}
        if missing_roles:
            loaded_roles, loaded_titles = await self._load_layout_maps(
                user_id, missing_roles, db
            )
        loaded_types: dict[UUID, str] = {}
        if missing_types:
            loaded_types = await self._load_recipe_types(user_id, missing_types, db)
        return (
            self._layout_candidate_roles(candidates, pinned, loaded_roles),
            self._layout_candidate_titles(candidates, pinned, loaded_titles),
            self._layout_candidate_types(candidates, pinned, loaded_types),
        )

    async def _resume_layout_maps(
        self,
        saved: dict[str, Any],
        user_id: UUID,
        db: AsyncSession,
    ) -> tuple[dict[UUID, list[str]], dict[UUID, str], dict[UUID, str]]:
        saved_ids = self._checkpoint_saved_ids(saved)
        roles, titles, types = self._maps_from_checkpoint(saved)
        roles_present = isinstance(saved.get("roles"), dict)
        titles_present = isinstance(saved.get("titles"), dict)
        types_present = isinstance(saved.get("types"), dict)
        missing_roles = [
            recipe_id
            for recipe_id in saved_ids
            if not roles_present
            or recipe_id not in roles
            or not titles_present
            or recipe_id not in titles
        ]
        missing_types = [
            recipe_id
            for recipe_id in saved_ids
            if not types_present or not types.get(recipe_id)
        ]
        if missing_roles:
            loaded_roles, loaded_titles = await self._load_layout_maps(
                user_id, missing_roles, db
            )
            for recipe_id in missing_roles:
                if recipe_id not in roles:
                    roles[recipe_id] = loaded_roles.get(recipe_id, [])
                if recipe_id not in titles:
                    titles[recipe_id] = loaded_titles.get(recipe_id, "")
        if missing_types:
            loaded_types = await self._load_recipe_types(user_id, missing_types, db)
            for recipe_id in missing_types:
                if not types.get(recipe_id):
                    types[recipe_id] = loaded_types.get(recipe_id, "")
        return roles, titles, types

    @staticmethod
    def _checkpoint_saved_ids(saved: dict[str, Any]) -> list[UUID]:
        raw = saved.get("handles")
        if not isinstance(raw, dict):
            return []
        ids: list[UUID] = []
        seen: set[UUID] = set()
        for value in raw.values():
            recipe_id = value if isinstance(value, UUID) else UUID(str(value))
            if recipe_id in seen:
                continue
            seen.add(recipe_id)
            ids.append(recipe_id)
        return ids

    @staticmethod
    def _maps_from_checkpoint(
        saved: dict[str, Any],
    ) -> tuple[dict[UUID, list[str]], dict[UUID, str], dict[UUID, str]]:
        roles: dict[UUID, list[str]] = {}
        titles: dict[UUID, str] = {}
        types: dict[UUID, str] = {}
        raw_roles = saved.get("roles")
        raw_titles = saved.get("titles")
        raw_types = saved.get("types")
        if isinstance(raw_roles, dict):
            for key, value in raw_roles.items():
                names = value if isinstance(value, list) else []
                roles[UUID(str(key))] = [str(role) for role in names]
        if isinstance(raw_titles, dict):
            for key, value in raw_titles.items():
                titles[UUID(str(key))] = str(value)
        if isinstance(raw_types, dict):
            for key, value in raw_types.items():
                types[UUID(str(key))] = str(value or "")
        return roles, titles, types

    @staticmethod
    def _candidate_ids(
        candidates: list[object],
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
    ) -> list[UUID]:
        ids: list[UUID] = []
        seen: set[UUID] = set()
        for candidate in candidates:
            recipe_id = getattr(candidate, "recipe_id", None)
            if isinstance(recipe_id, UUID) and recipe_id not in seen:
                seen.add(recipe_id)
                ids.append(recipe_id)
        for recipe_id in pinned:
            if recipe_id not in seen:
                seen.add(recipe_id)
                ids.append(recipe_id)
        return ids

    @staticmethod
    def _layout_candidate_types(
        candidates: list[object],
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
        loaded: Mapping[UUID, str],
    ) -> dict[UUID, str]:
        types: dict[UUID, str] = {}
        for candidate in candidates:
            if not isinstance(candidate, RecipeCandidate):
                continue
            if candidate.recipe_type:
                types[candidate.recipe_id] = str(candidate.recipe_type)
        for recipe_id, snap in pinned.items():
            if recipe_id in types:
                continue
            recipe_type = snap.recipe_type
            types[recipe_id] = (
                recipe_type.value if hasattr(recipe_type, "value") else str(recipe_type)
            )
        for recipe_id, recipe_type in loaded.items():
            if recipe_type and recipe_id not in types:
                types[recipe_id] = recipe_type
        return types

    @staticmethod
    def _saved_calories(
        candidates: list[object],
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
    ) -> dict[UUID, float]:
        calories: dict[UUID, float] = {}
        for candidate in candidates:
            if not isinstance(candidate, RecipeCandidate):
                continue
            if candidate.macro_summary.calories is None:
                continue
            calories[candidate.recipe_id] = float(candidate.macro_summary.calories)
        for recipe_id, snap in pinned.items():
            if snap.calories is None or recipe_id in calories:
                continue
            calories[recipe_id] = float(snap.calories)
        return calories

    async def _load_recipe_types(
        self,
        user_id: UUID,
        recipe_ids: list[UUID],
        db: AsyncSession,
    ) -> dict[UUID, str]:
        if not recipe_ids:
            return {}
        result = await db.execute(
            select(Recipe.id, Recipe.recipe_type).where(
                Recipe.user_id == user_id,
                Recipe.deleted_at.is_(None),
                Recipe.id.in_(recipe_ids),
            )
        )
        types: dict[UUID, str] = {}
        for recipe_id, recipe_type in result.all():
            types[recipe_id] = (
                recipe_type.value if hasattr(recipe_type, "value") else str(recipe_type)
            )
        return types

    async def _load_layout_maps(
        self,
        user_id: UUID,
        recipe_ids: list[UUID],
        db: AsyncSession,
    ) -> tuple[dict[UUID, list[str]], dict[UUID, str]]:
        if not recipe_ids:
            return {}, {}
        result = await db.execute(
            select(Recipe.id, Recipe.name, RecipeMealDetails.meal_roles)
            .join(RecipeMealDetails, RecipeMealDetails.recipe_id == Recipe.id)
            .where(
                Recipe.user_id == user_id,
                Recipe.deleted_at.is_(None),
                Recipe.id.in_(recipe_ids),
            )
        )
        roles: dict[UUID, list[str]] = {}
        titles: dict[UUID, str] = {}
        for recipe_id, name, meal_roles in result.all():
            roles[recipe_id] = _role_names(meal_roles)
            titles[recipe_id] = str(name)
        return roles, titles

    @staticmethod
    def _build_handles(
        candidates: list[object], pins: list[Pin]
    ) -> dict[str, UUID]:
        handles: dict[str, UUID] = {}
        seen: set[UUID] = set()
        number = 1
        for candidate in candidates:
            recipe_id = getattr(candidate, "recipe_id", None)
            if not isinstance(recipe_id, UUID) or recipe_id in seen:
                continue
            handles[f"R{number}"] = recipe_id
            seen.add(recipe_id)
            number += 1
        for pin in pins:
            if pin.recipe_id in seen:
                continue
            handles[f"R{number}"] = pin.recipe_id
            seen.add(pin.recipe_id)
            number += 1
        return handles

    async def _load_pins(
        self,
        assignments: list[Any],
        user_id: UUID,
        db: AsyncSession,
    ) -> tuple[list[Pin], dict[UUID, PinnedRecipeSnapshot]]:
        requests: list[tuple[int, str, UUID, str]] = []
        for item in assignments:
            parsed = self._assignment_identity(item)
            if parsed is not None:
                requests.append(parsed)
        if not requests:
            return [], {}
        names = {recipe_id: name for _day, _slot, recipe_id, name in requests}
        loaded = await RecipeService().load_pinned_recipes(
            user_id,
            [recipe_id for _day, _slot, recipe_id, _name in requests],
            db,
            names=names,
        )
        pins = [
            Pin(
                day_number=day,
                slot=slot,
                recipe_id=recipe_id,
                recipe_type=loaded[recipe_id].recipe_type.value,
            )
            for day, slot, recipe_id, _name in requests
        ]
        return pins, loaded

    @staticmethod
    def _assignment_identity(item: Any) -> tuple[int, str, UUID, str] | None:
        if hasattr(item, "day") and getattr(item, "recipe_id", None):
            raw_id = item.recipe_id
            recipe_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
            name = getattr(item, "recipe_name", None) or str(recipe_id)
            return int(item.day), str(item.slot_type), recipe_id, str(name)
        if isinstance(item, dict) and item.get("recipe_id"):
            recipe_id = UUID(str(item["recipe_id"]))
            name = item.get("recipe_name") or str(recipe_id)
            return int(item["day"]), str(item["slot_type"]), recipe_id, str(name)
        return None

    @staticmethod
    def _assert_pins_allowed(
        pins: list[Pin],
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
        exclusion_views: tuple[ExclusionView, ...],
    ) -> None:
        if not pins or not exclusion_views:
            return
        checker = ExclusionChecker()
        for pin in pins:
            snap = pinned[pin.recipe_id]
            view = RecipeView(
                id=snap.recipe_id,
                ingredients=tuple(
                    RecipeIngredientView(
                        name=ingredient.name,
                        ingredient_id=ingredient.ingredient_id,
                    )
                    for ingredient in snap.ingredients
                ),
            )
            hit = checker.first_violation(view, exclusion_views)
            if hit is None:
                continue
            _ingredient_name, exclusion_name = hit
            raise PlanGenerationFailedError(
                f"Pinned recipe '{snap.title}' contains excluded ingredient "
                f"'{exclusion_name}'. Remove the pin or the exclusion."
            )

    @staticmethod
    async def _load_juice_configs(
        plan_id: UUID, db: AsyncSession
    ) -> list[JuiceSlotConfig]:
        result = await db.execute(
            select(JuicingConfig)
            .where(JuicingConfig.plan_id == plan_id)
            .order_by(JuicingConfig.slot_order.asc(), JuicingConfig.time_of_day.asc())
        )
        configs: list[JuiceSlotConfig] = []
        for row in result.scalars().all():
            time_of_day = (
                row.time_of_day.value
                if hasattr(row.time_of_day, "value")
                else str(row.time_of_day)
            )
            configs.append(
                JuiceSlotConfig(
                    time_of_day=time_of_day,
                    size_ml=ml_for_juice_size(row.size),
                    slot_order=int(row.slot_order),
                )
            )
        return configs

    def _apply_skeleton(
        self,
        plan: GeneratedPlanData,
        skeleton: PlanSkeleton,
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
        *,
        strict: bool = True,
    ) -> GeneratedPlanData:
        pairs, errors = match_skeleton(plan, skeleton)
        if strict and errors:
            raise PlanGenerationFailedError("Layout: " + "; ".join(errors))
        if strict:
            return self._stamp_matched_skeleton(plan, pairs, pinned)
        return self._apply_skeleton_loose(plan, skeleton, pinned)

    def _stamp_matched_skeleton(
        self,
        plan: GeneratedPlanData,
        pairs: list[tuple[SkeletonSlot, GeneratedPlanItemAI]],
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
    ) -> GeneratedPlanData:
        """Stamp juice size and pins onto the model's items and keep their order."""
        stamped_by_item = {
            id(item): self._stamp_skeleton_slot(item, slot, pinned)
            for slot, item in pairs
        }
        new_days: list[GeneratedPlanDayAI] = []
        for day in plan.days:
            new_items: list[GeneratedPlanItemAI] = []
            for item in day.items:
                stamped = stamped_by_item.get(id(item))
                if stamped is None:
                    raise PlanGenerationFailedError(
                        f"Layout: Day {day.day_number} extra {item.slot_type} "
                        f"'{item.recipe_title}'"
                    )
                new_items.append(stamped)
            new_days.append(day.model_copy(update={"items": new_items}))
        return GeneratedPlanData(
            days=new_days,
            generated_recipes=plan.generated_recipes,
            review_notes=plan.review_notes,
        )

    def _apply_skeleton_loose(
        self,
        plan: GeneratedPlanData,
        skeleton: PlanSkeleton,
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
    ) -> GeneratedPlanData:
        by_day = {day.day_number: day for day in plan.days}
        new_days: list[GeneratedPlanDayAI] = []
        for day_number in sorted({slot.day_number for slot in skeleton.slots}):
            model_day = by_day.get(day_number)
            model_items = list(model_day.items) if model_day is not None else []
            used = [False] * len(model_items)
            new_items: list[GeneratedPlanItemAI] = []
            for slot in skeleton.for_day(day_number):
                index = self._take_skeleton_item(model_items, used, slot)
                base = model_items[index] if index is not None else None
                if index is not None:
                    used[index] = True
                stamped = self._stamp_skeleton_slot(base, slot, pinned)
                if stamped is not None:
                    new_items.append(stamped)
            new_days.append(GeneratedPlanDayAI(day_number=day_number, items=new_items))
        return GeneratedPlanData(
            days=new_days,
            generated_recipes=plan.generated_recipes,
            review_notes=plan.review_notes,
        )

    @staticmethod
    def _take_skeleton_item(
        items: list[GeneratedPlanItemAI],
        used: list[bool],
        slot: SkeletonSlot,
    ) -> int | None:
        for index, item in enumerate(items):
            if used[index] or item.slot_type != slot.slot:
                continue
            if (
                slot.juice_time
                and item.juice_time is not None
                and item.juice_time.value != slot.juice_time
            ):
                continue
            return index
        return None

    @staticmethod
    def _stamp_skeleton_slot(
        base: GeneratedPlanItemAI | None,
        slot: SkeletonSlot,
        pinned: Mapping[UUID, PinnedRecipeSnapshot],
    ) -> GeneratedPlanItemAI | None:
        if base is None and slot.pinned_recipe_id is None:
            return None
        snap = (
            pinned.get(slot.pinned_recipe_id)
            if slot.pinned_recipe_id is not None
            else None
        )
        if base is None:
            assert slot.pinned_recipe_id is not None
            base = GeneratedPlanItemAI(
                slot_type=slot.slot,  # type: ignore[arg-type]
                recipe_id=slot.pinned_recipe_id,
                recipe_title=snap.title if snap is not None else "Pinned recipe",
                servings=1,
            )
        updates: dict[str, Any] = {}
        if slot.kind in ("juice", "smoothie"):
            updates["juice_time"] = (
                JuiceTime(slot.juice_time) if slot.juice_time else None
            )
            updates["juice_size_ml"] = slot.juice_size_ml
        else:
            updates["juice_time"] = None
            updates["juice_size_ml"] = None
        if slot.pinned_recipe_id is not None:
            updates["recipe_id"] = slot.pinned_recipe_id
            if snap is not None:
                updates["recipe_title"] = snap.title
                if snap.calories is None:
                    updates["nutrition_unknown"] = True
                    updates["calories"] = None
                    updates["protein_g"] = None
                    updates["carbs_g"] = None
                    updates["fat_g"] = None
                    updates["fiber_g"] = None
        return base.model_copy(update=updates)
