"""AgentToolExecutor — docs/7_TECH_SPEC.md §5.2 / docs/2_SAD.md §6.4."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import structlog
from anthropic.types import ToolUseBlock
from pydantic import BaseModel, ValidationError
from schemas.agent import (
    AgentContext,
    ExpandRecipeInput,
    GenerateRecipeInput,
    GetNutritionalProfileInput,
    GetPlanExplanationInput,
    GetPlanInput,
    GetRecipeInput,
    GetShoppingListInput,
    GetUserProfileInput,
    ImportRecipeInput,
    PlanProposal,
    ProposeProfileUpdateInput,
    SaveRecipeInput,
    SearchRecipesInput,
    SwapMealInput,
    TriggerPlanGenerationInput,
    UpdatePantryInput,
)
from schemas.recipes import RecipeDraft as ServiceRecipeDraft
from schemas.recipes import RecipeFilters
from services.pantry_service import PantryService
from services.plan_service import PlanService
from services.profile_service import ProfileService
from services.recipe_service import RecipeService
from services.shopping_list_service import ShoppingListService
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

ToolHandler = Callable[
    [dict[str, Any], UUID, AsyncSession, AgentContext],
    Awaitable[Any],
]


def _serialize(value: Any) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if hasattr(value, "__table__"):
        # SQLAlchemy mapped instance — dump common columns via __dict__ keys
        data: dict[str, Any] = {}
        for key, raw in vars(value).items():
            if key.startswith("_"):
                continue
            if isinstance(raw, UUID):
                data[key] = str(raw)
            elif hasattr(raw, "value"):
                data[key] = raw.value
            elif hasattr(raw, "isoformat"):
                data[key] = raw.isoformat()
            elif isinstance(raw, (str, int, float, bool, type(None), list, dict)):
                data[key] = raw
            else:
                data[key] = str(raw)
        return json.dumps(data, default=str)
    if isinstance(value, list):
        return json.dumps(
            [json.loads(_serialize(v)) if not isinstance(v, str) else v for v in value],
            default=str,
        )
    return json.dumps(value, default=str)


def _tool_result(
    tool_use_id: str, content: str, *, is_error: bool = False
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
    }
    if is_error:
        result["is_error"] = True
    return result


async def _handle_trigger_plan_generation(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    """Fill the generate form. Does not enqueue — user confirms in the UI."""
    data = TriggerPlanGenerationInput.model_validate(raw)
    profile = await ProfileService().get_profile(user_id, db)
    juicing = (
        data.include_juicing
        if data.include_juicing is not None
        else profile.juicing_enabled
    )
    proposal = PlanProposal(
        num_days=data.duration_days,
        diet_type=data.diet_type or profile.diet_type,
        cooking_type=data.cooking_type or profile.cooking_type,
        calorie_target=(
            data.calorie_target
            if data.calorie_target is not None
            else profile.calorie_target
        ),
        recipe_usage_policy=data.sourcing_policy or profile.recipe_usage_policy,
        include_juicing=juicing,
        notes=data.notes,
    )
    return {
        "status": "awaiting_confirmation",
        "proposal": proposal.model_dump(mode="json"),
    }


async def _handle_get_plan(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    data = GetPlanInput.model_validate(raw)
    return await PlanService().get_plan(data.plan_id, user_id, db)


async def _handle_swap_meal(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    data = SwapMealInput.model_validate(raw)
    return await PlanService().swap_plan_item(
        data.plan_id, data.item_id, user_id, data.new_recipe_id, db
    )


async def _handle_generate_recipe(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    from schemas.agent import RecipeGenerationRequest

    from agent.recipe_generator import RecipeGeneratorAgent

    data = GenerateRecipeInput.model_validate(raw)
    request = RecipeGenerationRequest(
        title=data.title,
        description=data.description,
        diet_type=data.diet_type,
        prep_type=data.prep_type,
        is_juicing=data.is_juicing,
    )
    draft = await RecipeGeneratorAgent().generate(user_id, request, db)
    return draft.model_dump(mode="json")


async def _handle_get_recipe(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    data = GetRecipeInput.model_validate(raw)
    return await RecipeService().get_recipe(data.recipe_id, user_id, db)


async def _handle_search_recipes(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    from search.recipe_search_service import RecipeSearchService

    data = SearchRecipesInput.model_validate(raw)
    filters = RecipeFilters(q=data.query, limit=data.limit)
    page = await RecipeSearchService().search(user_id, data.query, filters, db)
    return {
        "total": page.total,
        "offset": page.offset,
        "limit": page.limit,
        "data": [
            {
                "id": str(r.id),
                "name": r.name,
                "recipe_type": r.recipe_type.value,
                "description": r.description,
            }
            for r in page.data
        ],
    }


async def _handle_save_recipe(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    from search.recipe_search_service import RecipeSearchService

    data = SaveRecipeInput.model_validate(raw)
    draft = ServiceRecipeDraft.model_validate(data.draft)
    recipe = await RecipeService().save_recipe(user_id, draft, db)
    try:
        await RecipeSearchService().embed_recipe(recipe, db)
    except Exception as exc:
        logger.exception(
            "recipe_embed_failed_soft",
            recipe_id=str(recipe.id),
            error=str(exc),
            trace_id=context.trace_id,
        )
    return {"recipe_id": str(recipe.id), "name": recipe.name}


async def _handle_import_recipe(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    from agent.recipe_importer import RecipeImporterAgent

    data = ImportRecipeInput.model_validate(raw)
    importer = RecipeImporterAgent()
    if data.file_url:
        draft = await importer.import_from_image(user_id, data.file_url, db)
    elif data.text:
        draft = await importer.import_from_text(user_id, data.text, db)
    else:
        raise ValueError("import_recipe requires text or file_url")
    return draft.model_dump(mode="json")


async def _handle_expand_recipe(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    from schemas.agent import RecipeGenerationRequest

    from agent.recipe_generator import RecipeGeneratorAgent

    data = ExpandRecipeInput.model_validate(raw)
    request = RecipeGenerationRequest(
        description=data.instruction,
        recipe_id=data.recipe_id,
    )
    draft = await RecipeGeneratorAgent().generate(user_id, request, db)
    return draft.model_dump(mode="json")


async def _handle_get_nutritional_profile(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    data = GetNutritionalProfileInput.model_validate(raw)
    recipe = await RecipeService().get_recipe(data.recipe_id, user_id, db)
    from db.models import RecipeNutrition

    nutrition = await db.get(RecipeNutrition, recipe.id)
    if nutrition is None:
        return {"recipe_id": str(recipe.id), "nutrition": None}
    return {
        "recipe_id": str(recipe.id),
        "calories_per_serving": str(nutrition.calories_per_serving),
        "protein_g": str(nutrition.protein_g),
        "carbs_g": str(nutrition.carbs_g),
        "fat_g": str(nutrition.fat_g),
        "fiber_g": str(nutrition.fiber_g),
        "nutritional_highlights": nutrition.nutritional_highlights,
    }


async def _handle_get_plan_explanation(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    from agent.plan_explainer import PlanExplainerAgent

    data = GetPlanExplanationInput.model_validate(raw)
    chunks: list[str] = []
    async for delta in PlanExplainerAgent().explain(data.plan_id, user_id, db):
        chunks.append(delta)
    return {"explanation": "".join(chunks)}


async def _handle_propose_profile_update(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    data = ProposeProfileUpdateInput.model_validate(raw)
    # Interaction tool — does NOT write. User must confirm separately.
    return {
        "proposed_updates": data.updates,
        "requires_confirmation": True,
        "message": "Present these proposed profile changes to the user for confirmation.",
    }


async def _handle_update_pantry(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    data = UpdatePantryInput.model_validate(raw)
    pantry = PantryService()
    if data.action == "add":
        if data.ingredient_id is None:
            raise ValueError("ingredient_id required for pantry add")
        item = await pantry.add_item(user_id, data.ingredient_id, db)
        return {"item_id": str(item.id), "action": "added"}
    if data.item_id is None:
        raise ValueError("item_id required for pantry remove")
    await pantry.remove_item(data.item_id, user_id, db)
    return {"item_id": str(data.item_id), "action": "removed"}


async def _handle_get_shopping_list(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    data = GetShoppingListInput.model_validate(raw)
    items = await ShoppingListService().generate(data.plan_id, user_id, db)
    return [
        {
            "id": str(i.id),
            "ingredient_id": str(i.ingredient_id) if i.ingredient_id else None,
            "ingredient_name_display": i.ingredient_name_display,
            "quantity": str(i.quantity_total) if i.quantity_total is not None else None,
            "unit": i.unit,
            "is_checked": i.is_checked,
        }
        for i in items
    ]


async def _handle_get_user_profile(
    raw: dict[str, Any],
    user_id: UUID,
    db: AsyncSession,
    context: AgentContext,
) -> Any:
    GetUserProfileInput.model_validate(raw or {})
    profile = await ProfileService().get_profile(user_id, db)
    exclusions = await ProfileService().get_exclusions(user_id, db)
    return {
        "diet_type": profile.diet_type.value,
        "cooking_type": profile.cooking_type.value,
        "calorie_target": profile.calorie_target,
        "protein_g_target": str(profile.protein_g_target)
        if profile.protein_g_target is not None
        else None,
        "carbs_g_target": str(profile.carbs_g_target)
        if profile.carbs_g_target is not None
        else None,
        "fat_g_target": str(profile.fat_g_target)
        if profile.fat_g_target is not None
        else None,
        "fiber_g_target": str(profile.fiber_g_target)
        if profile.fiber_g_target is not None
        else None,
        "tier": profile.tier.value,
        "juicing_enabled": profile.juicing_enabled,
        "exclusions": [
            {
                "ingredient_id": str(e.ingredient_id) if e.ingredient_id else None,
                "ingredient_name_raw": e.ingredient_name_raw,
            }
            for e in exclusions
        ],
    }


# Populated at import time — no dynamic dispatch magic (docs/7_TECH_SPEC.md §5.2).
TOOL_REGISTRY: dict[str, ToolHandler] = {
    "trigger_plan_generation": _handle_trigger_plan_generation,
    "get_plan": _handle_get_plan,
    "swap_meal": _handle_swap_meal,
    "generate_recipe": _handle_generate_recipe,
    "get_recipe": _handle_get_recipe,
    "search_recipes": _handle_search_recipes,
    "save_recipe": _handle_save_recipe,
    "import_recipe": _handle_import_recipe,
    "expand_recipe": _handle_expand_recipe,
    "get_nutritional_profile": _handle_get_nutritional_profile,
    "get_plan_explanation": _handle_get_plan_explanation,
    "propose_profile_update": _handle_propose_profile_update,
    "update_pantry": _handle_update_pantry,
    "get_shopping_list": _handle_get_shopping_list,
    "get_user_profile": _handle_get_user_profile,
}

TOOL_INPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "trigger_plan_generation": TriggerPlanGenerationInput,
    "get_plan": GetPlanInput,
    "swap_meal": SwapMealInput,
    "generate_recipe": GenerateRecipeInput,
    "get_recipe": GetRecipeInput,
    "search_recipes": SearchRecipesInput,
    "save_recipe": SaveRecipeInput,
    "import_recipe": ImportRecipeInput,
    "expand_recipe": ExpandRecipeInput,
    "get_nutritional_profile": GetNutritionalProfileInput,
    "get_plan_explanation": GetPlanExplanationInput,
    "propose_profile_update": ProposeProfileUpdateInput,
    "update_pantry": UpdatePantryInput,
    "get_shopping_list": GetShoppingListInput,
    "get_user_profile": GetUserProfileInput,
}


def chat_tool_definitions() -> list[dict[str, Any]]:
    """Anthropic tool schemas derived from Pydantic models (docs/2_SAD.md §6.4)."""
    tools: list[dict[str, Any]] = []
    descriptions = {
        "trigger_plan_generation": (
            "Fill the on-screen plan generation form from this conversation. "
            "Does not start generation. The user reviews diet, cooking type, "
            "juicing, and notes, then presses Generate. Never write a day-by-day "
            "meal plan in chat — the structured generator builds the actual week "
            "after they confirm."
        ),
        "get_plan": "Retrieve an existing meal plan by ID.",
        "swap_meal": "Replace a single meal slot recipe in a plan.",
        "generate_recipe": "Generate a structured recipe draft (not yet saved).",
        "get_recipe": "Retrieve a saved recipe by ID.",
        "search_recipes": "Search the user's saved recipe library.",
        "save_recipe": "Persist a recipe draft to the user's library.",
        "import_recipe": "Extract a recipe draft from text or an image URL.",
        "expand_recipe": "Expand or vary an existing recipe into a full draft.",
        "get_nutritional_profile": "Return stored nutrition for a recipe.",
        "get_plan_explanation": "Explain why a plan fits the user's profile.",
        "propose_profile_update": "Propose profile changes for user confirmation (does not write).",
        "update_pantry": "Add or remove a pantry item.",
        "get_shopping_list": "Build the shopping list for a plan.",
        "get_user_profile": "Return the current user's profile and exclusions.",
    }
    for name, schema_cls in TOOL_INPUT_SCHEMAS.items():
        tools.append(
            {
                "name": name,
                "description": descriptions[name],
                "input_schema": schema_cls.model_json_schema(),
            }
        )
    return tools


class AgentToolExecutor:
    def __init__(self, registry: dict[str, ToolHandler] | None = None) -> None:
        self._registry = registry or TOOL_REGISTRY

    async def execute(
        self,
        tool_use_block: ToolUseBlock,
        user_id: UUID,
        db: AsyncSession,
        context: AgentContext,
    ) -> dict[str, Any]:
        tool_name = tool_use_block.name
        tool_use_id = tool_use_block.id
        raw_input = dict(tool_use_block.input or {})
        # Security invariant: ignore any user_id the model supplies.
        raw_input.pop("user_id", None)

        started = time.perf_counter()
        handler = self._registry.get(tool_name)
        if handler is None:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "tool_call",
                tool_name=tool_name,
                duration_ms=duration_ms,
                success=False,
                trace_id=context.trace_id,
                error="unknown_tool",
            )
            return _tool_result(
                tool_use_id,
                f"Unknown tool: {tool_name}",
                is_error=True,
            )

        schema_cls = TOOL_INPUT_SCHEMAS.get(tool_name)
        try:
            if schema_cls is not None:
                schema_cls.model_validate(raw_input)
            result = await handler(raw_input, user_id, db, context)
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "tool_call",
                tool_name=tool_name,
                duration_ms=duration_ms,
                success=True,
                trace_id=context.trace_id,
                user_id=str(user_id),
            )
            return _tool_result(tool_use_id, _serialize(result))
        except ValidationError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "tool_call",
                tool_name=tool_name,
                duration_ms=duration_ms,
                success=False,
                trace_id=context.trace_id,
                error="validation_error",
            )
            return _tool_result(
                tool_use_id,
                f"Invalid tool input: {exc}",
                is_error=True,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.exception(
                "tool_call",
                tool_name=tool_name,
                duration_ms=duration_ms,
                success=False,
                trace_id=context.trace_id,
                error=type(exc).__name__,
            )
            return _tool_result(
                tool_use_id,
                f"Tool error: {type(exc).__name__}: {exc}",
                is_error=True,
            )
