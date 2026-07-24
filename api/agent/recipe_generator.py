"""RecipeGeneratorAgent — docs/7_TECH_SPEC.md §5.5."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.client import AnthropicClient
from config import AgentTask, route_model, settings
from exceptions import NutritionOutOfRangeError
from preprocessing.exclusion_service import ExclusionService
from schemas.agent import RecipeDraft, RecipeGenerationRequest
from services.profile_service import ProfileService
from services.recipe_service import RecipeService
from validation.exclusion_checker import ExclusionChecker
from validation.nutrition_validator import NutritionValidator
from validation.types import ExclusionView, NutritionPerServing

logger = structlog.get_logger(__name__)

_OUTPUT_RECIPE_TOOL: dict[str, Any] = {
    "name": "output_recipe",
    "description": "Return the complete recipe as structured JSON.",
    "input_schema": {},  # filled below after helper
}


def _recipe_output_schema() -> dict[str, Any]:
    """Tech-spec recipe JSON without post-parse fields (ingredient_id, unresolved)."""
    schema = RecipeDraft.model_json_schema()
    props = schema.get("properties", {})
    props.pop("unresolved_ingredient_names", None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [
            r for r in required if r != "unresolved_ingredient_names"
        ]
    # Nested ingredient defs may include ingredient_id — strip from $defs if present.
    defs = schema.get("$defs") or schema.get("definitions") or {}
    for defn in defs.values():
        if not isinstance(defn, dict):
            continue
        dprops = defn.get("properties")
        if isinstance(dprops, dict):
            dprops.pop("ingredient_id", None)
    return schema


_OUTPUT_RECIPE_TOOL["input_schema"] = _recipe_output_schema()



class RecipeGeneratorAgent:
    def __init__(
        self,
        client: AnthropicClient | None = None,
        exclusion_checker: ExclusionChecker | None = None,
        nutrition_validator: NutritionValidator | None = None,
        exclusion_service: ExclusionService | None = None,
    ) -> None:
        self._client = client or AnthropicClient()
        self._exclusions = exclusion_checker or ExclusionChecker()
        self._nutrition = nutrition_validator or NutritionValidator()
        self._exclusion_service = exclusion_service or ExclusionService()

    async def generate(
        self,
        user_id: UUID,
        request: RecipeGenerationRequest,
        db: AsyncSession,
    ) -> RecipeDraft:
        profile = await ProfileService().get_profile(user_id, db)
        exclusion_rows = await ProfileService().get_exclusions(user_id, db)
        exclusion_views = tuple(
            ExclusionView(
                raw_name=e.ingredient_name_raw or "",
                ingredient_id=e.ingredient_id,
            )
            for e in exclusion_rows
        )
        exclusion_constraint = self._exclusions.format_constraint_string(
            exclusion_views
        )

        expand_context: dict[str, Any] | None = None
        if request.recipe_id is not None:
            recipe = await RecipeService().get_recipe(request.recipe_id, user_id, db)
            expand_context = {
                "id": str(recipe.id),
                "name": recipe.name,
                "description": recipe.description,
                "servings": recipe.servings,
                "prep_method": recipe.prep_method.value
                if recipe.prep_method
                else None,
                "cooking_type": recipe.cooking_type.value,
            }

        system_prompt = (
            "You are Nouri's recipe generation engine. Produce one complete, "
            "plant-based-appropriate recipe by calling the output_recipe tool "
            "exactly once, matching the request below.\n\n"
            "Hard constraint: never include an ingredient listed in "
            "exclusion_constraints, in any form — whole, ground, as a derivative, or "
            "hidden inside a compound item like a sauce or stock.\n\n"
            "Ingredients must have real-world accurate quantities and units for the "
            "stated servings. Steps must be complete and independently followable — "
            'no "cook until done" without a method and a rough time. '
            "nutrition_per_serving must be a realistic estimate for the ingredients "
            "and quantities you wrote, not a generic template value.\n\n"
            "diet_type and prep_type on the recipe must match what's requested (or "
            "the user's profile default if not specified). If expand_from_recipe is "
            "present, treat this as a variation of that recipe — same core identity, "
            "changed per the instruction — not an unrelated recipe that happens to "
            "share a name.\n\n"
            "Call output_recipe once you have the complete recipe. Do not include "
            "commentary outside the tool call.\n"
            f"<exclusion_constraints>{exclusion_constraint}</exclusion_constraints>"
        )
        user_payload = {
            "title": request.title,
            "description": request.description,
            "diet_type": (request.diet_type or profile.diet_type).value,
            "prep_type": request.prep_type.value if request.prep_type else None,
            "is_juicing": request.is_juicing,
            "expand_from_recipe": expand_context,
        }
        user_prompt = (
            "Generate a recipe from the request below.\n"
            f"<request>{json.dumps(user_payload, default=str)}</request>"
        )

        draft = await self._call_and_parse(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=route_model(AgentTask.RECIPE_GENERATION),
        )

        draft = await self._validate_nutrition(draft, system_prompt)
        draft = await self._resolve_ingredients(draft, db)
        return draft

    async def _call_and_parse(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        trace_id: str | None = None,
    ) -> RecipeDraft:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_prompt}
        ]
        for parse_attempt in range(2):
            message = await self._client.complete(
                messages,
                model=model,
                tools=[_OUTPUT_RECIPE_TOOL],
                tool_choice={"type": "tool", "name": "output_recipe"},
                max_tokens=4096,
                system=system_prompt,
                trace_id=trace_id,
            )
            try:
                return self._extract_recipe(message)
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
                            f"Previous output failed validation: {exc}. Call output_recipe "
                            "again with the complete, valid recipe — same content, corrected "
                            "structure."
                        ),
                    }
                )
        raise ValueError("Failed to parse recipe output")

    def _extract_recipe(self, message: Any) -> RecipeDraft:
        for block in message.content:
            if block.type == "tool_use" and block.name == "output_recipe":
                return RecipeDraft.model_validate(block.input)
        raise ValueError("Model did not call output_recipe")

    async def _validate_nutrition(
        self, draft: RecipeDraft, system_prompt: str
    ) -> RecipeDraft:
        nutrition = NutritionPerServing(
            calories_kcal=draft.nutrition_per_serving.calories_kcal,
            protein_g=draft.nutrition_per_serving.protein_g,
            fat_g=draft.nutrition_per_serving.fat_g,
            carbohydrates_g=draft.nutrition_per_serving.carbohydrates_g,
            fiber_g=draft.nutrition_per_serving.fiber_g,
        )
        try:
            self._nutrition.check(nutrition)
            return draft
        except NutritionOutOfRangeError as exc:
            logger.warning(
                "nutrition_out_of_range",
                field=exc.field,
                value=exc.value,
            )
            if not settings.nutrition_reestimate_on_low_confidence:
                raise
            reestimate_prompt = (
                f"nutrition_per_serving.{exc.field} was estimated as {exc.value}, which "
                "is outside a plausible range for a single serving. Re-estimate "
                "nutrition_per_serving for this exact recipe — same ingredients and "
                "quantities, don't change the recipe itself — and call output_recipe "
                "again with corrected, realistic values.\n"
                f"<previous_draft>{draft.model_dump_json()}</previous_draft>"
            )
            return await self._call_and_parse(
                system_prompt=system_prompt,
                user_prompt=reestimate_prompt,
                model=route_model(AgentTask.RECIPE_GENERATION),
            )

    async def _resolve_ingredients(
        self, draft: RecipeDraft, db: AsyncSession
    ) -> RecipeDraft:
        unresolved: list[str] = []
        resolved_ings = []
        for ing in draft.ingredients:
            ingredient_id = await self._exclusion_service.resolve_name(
                ing.ingredient_name, db
            )
            if ingredient_id is None:
                unresolved.append(ing.ingredient_name)
            resolved_ings.append(
                ing.model_copy(update={"ingredient_id": ingredient_id})
            )
        return draft.model_copy(
            update={
                "ingredients": resolved_ings,
                "unresolved_ingredient_names": unresolved,
            }
        )
