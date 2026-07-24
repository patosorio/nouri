"""PlanGeneratorAgent — docs/7_TECH_SPEC.md §5.4 / RISK-07."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.client import AnthropicClient
from config import AgentTask, route_model, settings
from exceptions import PlanGenerationFailedError
from preprocessing.notes_preprocessor import NotesPreprocessor, RecipeTitleRef
from schemas.agent import (
    GeneratedPlanData,
    GeneratedRecipeAI,
    PlanGenerationJob,
    RepairInstructions,
)
from search.recipe_search_service import RecipeCandidate, RecipeSearchService
from services.profile_service import ProfileService
from services.recipe_service import RecipeService
from validation.plan_validator import PlanValidator
from validation.repair_strategy import RepairStrategy
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

logger = structlog.get_logger(__name__)

_OUTPUT_PLAN_TOOL: dict[str, Any] = {
    "name": "output_plan",
    "description": "Return the complete meal plan as structured JSON.",
    "input_schema": {},  # filled below
}


def _plan_output_schema() -> dict[str, Any]:
    schema = GeneratedPlanData.model_json_schema()
    defs = schema.get("$defs") or schema.get("definitions") or {}
    for defn in defs.values():
        if not isinstance(defn, dict):
            continue
        props = defn.get("properties")
        if isinstance(props, dict):
            props.pop("assigned_id", None)
    return schema


_OUTPUT_PLAN_TOOL["input_schema"] = _plan_output_schema()



class PlanGeneratorAgent:
    def __init__(
        self,
        client: AnthropicClient | None = None,
        notes_preprocessor: NotesPreprocessor | None = None,
        recipe_search: RecipeSearchService | None = None,
        plan_validator: PlanValidator | None = None,
        repair_strategy: RepairStrategy | None = None,
    ) -> None:
        self._client = client or AnthropicClient()
        self._notes = notes_preprocessor or NotesPreprocessor()
        self._search = recipe_search or RecipeSearchService()
        self._validator = plan_validator or PlanValidator()
        self._repair = repair_strategy or RepairStrategy()

    async def generate(
        self, job_payload: PlanGenerationJob, db: AsyncSession
    ) -> GeneratedPlanData:
        profile = await ProfileService().get_profile(job_payload.user_id, db)
        exclusions_rows = await ProfileService().get_exclusions(
            job_payload.user_id, db
        )
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

        candidates = await self._search.find_candidates(
            job_payload.user_id,
            job_payload.diet_type.value,
            job_payload.duration_days,
            db,
        )
        candidate_summaries = self._summarise_candidates(candidates)

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
            "hard_slot_assignments": hard_slot_assignments,
            "soft_notes_context": soft_notes_context,
            "duration_days": job_payload.duration_days,
        }

        system_prompt = (
            f"You are Nouri's meal-plan generation engine. Given a user's profile, "
            f"macro targets, and a candidate recipe pool, produce a complete "
            f"{job_payload.duration_days}-day meal plan by calling the output_plan "
            "tool exactly once.\n\n"
            "Hard constraints — never violate these:\n"
            "- Never include an ingredient listed in exclusions. This is checked "
            "deterministically after generation; a plan that violates it is discarded "
            "and regenerated, so treat it as non-negotiable, not a preference.\n"
            "- Every item's slot_type must be one of: breakfast, lunch, dinner, snack, "
            "juice, extra_morning, extra_afternoon, extra_evening.\n"
            "- Every item's recipe_id must either be the UUID of a "
            "saved_recipe_candidate you were given, or the literal string "
            '"generate_new" if you\'re proposing a new recipe. Every "generate_new" '
            "item must have a matching entry (same title) in generated_recipes.\n\n"
            "Target constraints — aim for these; they're validated with tolerance and "
            "you may get a repair request if you miss:\n"
            "- Daily calories and macros (protein/carbs/fat/fiber) within ±20% of the "
            "targets in generation_context.\n"
            "- Overall raw/cooked ratio within ±10% of the cooking_type target (e.g. "
            "raw_80_cooked_20 means ~80% of the week's items are raw preparations).\n"
            "- No single protein source repeated more than 2 consecutive days; no "
            "single ingredient appears in more than 60% of the week's recipes.\n\n"
            "sourcing_policy governs how much you lean on saved_recipe_candidates vs "
            "generate_new:\n"
            "- prefer_saved: use a saved candidate whenever one reasonably fits the "
            "slot; only generate_new when nothing in the pool fits.\n"
            "- balanced: mix freely based on what best serves variety and the day's "
            "targets.\n"
            "- prefer_new: default to generate_new unless a saved candidate is a "
            "clearly better fit.\n\n"
            "hard_slot_assignments are user-specified and must be honored exactly as "
            "given — don't override them even if they conflict with macro targets; "
            "the validator only checks constraints those slots don't already satisfy. "
            "soft_notes_context is user color/preference — follow it where it doesn't "
            "conflict with the hard constraints above.\n\n"
            "Every generated_recipes entry must be a complete recipe (ingredients "
            "with quantities and units, ordered steps) — not a title placeholder. "
            "Match diet_type and prep_type to the request context.\n\n"
            "Call output_plan once you have the full plan. Do not include commentary "
            "outside the tool call."
        )
        user_prompt = (
            f"Generate a {job_payload.duration_days}-day meal plan from the context "
            "below. Use saved_recipe_candidates where sourcing_policy favors it; "
            "otherwise propose new recipes via generate_new. Respect "
            "hard_slot_assignments exactly and follow soft_notes_context where it "
            "doesn't conflict with the hard constraints in the system prompt.\n"
            f"<generation_context>{json.dumps(context_block, default=str)}</generation_context>"
        )

        plan_data = await self._call_and_parse(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            trace_id=job_payload.trace_id,
        )
        plan_data = self._assign_generated_recipe_ids(plan_data)

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
                else (profile.fiber_g_target or Decimal("0"))
            ),
        )
        user_view = UserProfileView(
            cooking_type=cooking.value,
            exclusions=exclusion_views,
        )

        max_repairs = settings.plan_max_repair_iterations
        for attempt in range(max_repairs + 1):
            draft_view = self._to_plan_draft_view(plan_data)
            result = self._validator.validate(draft_view, user_view, targets)
            if result.passed:
                logger.info(
                    "plan_generation_validated",
                    plan_id=str(job_payload.plan_id),
                    attempt=attempt,
                    trace_id=job_payload.trace_id,
                )
                return plan_data

            if attempt >= max_repairs:
                # RISK-07: never deliver a failing plan — raise for worker to fail job.
                logger.error(
                    "plan_validation_failure",
                    plan_id=str(job_payload.plan_id),
                    errors=list(result.errors),
                    trace_id=job_payload.trace_id,
                )
                raise PlanGenerationFailedError(
                    "Plan failed validation after "
                    f"{max_repairs} repair iterations: {'; '.join(result.errors)}"
                )

            repair = RepairInstructions.from_validation(
                result.repair_instructions
                if result.repair_instructions.instructions
                else self._repair.build_repair_instructions(result.checker_results)
            )
            repair_user = (
                f"The previous plan failed validation. Regenerate a corrected "
                f"{job_payload.duration_days}-day plan that fixes every issue in "
                "repair_instructions below, while preserving everything in failed_plan "
                "that already satisfies the constraints — don't restructure days or swap "
                "recipes that weren't flagged. Call output_plan once with the complete "
                "corrected plan.\n"
                f"<failed_plan>{plan_data.model_dump_json()}</failed_plan>\n"
                f"<repair_instructions>{repair.model_dump_json()}</repair_instructions>"
            )
            plan_data = await self._call_and_parse(
                system_prompt=system_prompt,
                user_prompt=repair_user,
                trace_id=job_payload.trace_id,
            )
            plan_data = self._assign_generated_recipe_ids(plan_data)

        raise PlanGenerationFailedError()

    async def _call_and_parse(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        trace_id: str | None,
    ) -> GeneratedPlanData:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_prompt}
        ]
        model = route_model(AgentTask.PLAN_GENERATION)

        for parse_attempt in range(2):
            message = await self._client.complete(
                messages,
                model=model,
                tools=[_OUTPUT_PLAN_TOOL],
                tool_choice={"type": "tool", "name": "output_plan"},
                max_tokens=8192,
                system=system_prompt,
                trace_id=trace_id,
            )
            try:
                return self._extract_plan(message)
            except Exception as exc:
                if parse_attempt >= 1:
                    raise
                messages.append(
                    {"role": "assistant", "content": message.content}
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Previous output failed schema validation: {exc}. Call output_plan "
                            "again with the complete, valid plan — same content, corrected "
                            "structure."
                        ),
                    }
                )
        raise PlanGenerationFailedError("Failed to parse plan output")

    def _extract_plan(self, message: Any) -> GeneratedPlanData:
        for block in message.content:
            if block.type == "tool_use" and block.name == "output_plan":
                return GeneratedPlanData.model_validate(block.input)
        raise ValueError("Model did not call output_plan")

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

    def _to_plan_draft_view(self, plan: GeneratedPlanData) -> PlanDraftView:
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

        days: list[PlanDayView] = []
        for day in plan.days:
            items: list[PlanItemView] = []
            for item in day.items:
                rid: UUID | None
                if item.recipe_id == "generate_new":
                    rid = None
                else:
                    rid = item.recipe_id  # type: ignore[assignment]
                ingredients = (
                    recipe_ingredients.get(rid, ()) if rid is not None else ()
                )
                items.append(
                    PlanItemView(
                        day_number=day.day_number,
                        name=item.recipe_title,
                        slot=item.slot_type,
                        recipe_id=rid,
                        ingredients=ingredients,
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
        from schemas.recipes import RecipeFilters

        page = await RecipeService().list_recipes(
            user_id, RecipeFilters(limit=100, offset=0), db
        )
        return [RecipeTitleRef(id=r.id, name=r.name) for r in page.data]

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
    def _summarise_candidates(candidates: list[object]) -> list[dict[str, Any]]:
        """Token-efficient candidate summaries — title/macros/diet/prep only (§5.4)."""
        summaries: list[dict[str, Any]] = []
        for c in candidates[:30]:
            if isinstance(c, RecipeCandidate):
                macros = c.macro_summary
                summaries.append(
                    {
                        "recipe_id": str(c.recipe_id),
                        "title": c.title,
                        "diet_type": c.diet_type,
                        "cooking_type": c.cooking_type,
                        "calories": macros.calories,
                        "protein_g": macros.protein_g,
                        "carbs_g": macros.carbs_g,
                        "fat_g": macros.fat_g,
                        "similarity": c.similarity,
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
