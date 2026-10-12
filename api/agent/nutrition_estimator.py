"""NutritionEstimatorAgent — cheap structured nutrition fill for recipes (worker)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from config import AgentTask, route_model
from db.models import Ingredient, Recipe, RecipeIngredient
from exceptions import NutritionOutOfRangeError
from schemas.recipes import RecipeNutritionDraft
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from validation.nutrition_validator import NutritionValidator
from validation.types import NutritionPerServing

from agent.client import AnthropicClient

logger = structlog.get_logger(__name__)

_OUTPUT_NUTRITION_TOOL: dict[str, Any] = {
    "name": "output_nutrition",
    "description": "Return AI-estimated nutrition per serving for the recipe.",
    "input_schema": {
        "type": "object",
        "properties": {
            "calories_per_serving": {"type": "number"},
            "protein_g": {"type": "number"},
            "carbs_g": {"type": "number"},
            "fat_g": {"type": "number"},
            "fiber_g": {"type": "number"},
            "sat_fat_g": {"type": ["number", "null"]},
            "sugar_g": {"type": ["number", "null"]},
            "nutritional_highlights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                    "required": ["label"],
                },
            },
        },
        "required": [
            "calories_per_serving",
            "protein_g",
            "carbs_g",
            "fat_g",
            "fiber_g",
        ],
    },
}


class NutritionEstimatorAgent:
    """Estimates recipe_nutrition via haiku — AgentTask.NUTRITIONAL_PROFILE routing."""

    def __init__(self, client: AnthropicClient | None = None) -> None:
        self._client = client or AnthropicClient()
        self._nutrition = NutritionValidator()

    async def estimate(
        self,
        recipe: Recipe,
        db: AsyncSession,
        *,
        trace_id: str | None = None,
        job_id: UUID | None = None,
    ) -> RecipeNutritionDraft:
        ingredients = await db.execute(
            select(RecipeIngredient, Ingredient)
            .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
            .where(RecipeIngredient.recipe_id == recipe.id)
            .order_by(RecipeIngredient.sort_order.asc())
        )
        ingredient_lines = [
            {
                "name": ingredient.name,
                "amount": str(row.amount) if row.amount is not None else None,
                "unit": row.unit,
                "notes": row.notes,
            }
            for row, ingredient in ingredients.all()
        ]
        # PROMPT_TODO: nutrition estimation prompt — docs/7_TECH_SPEC.md / RISK-06.
        system = (
            "[PROMPT_TODO: NutritionEstimatorAgent system — estimate macros per "
            "serving from ingredient knowledge; food-advisor accuracy only.]\n"
            "Call output_nutrition with the estimate."
        )
        user = (
            "[PROMPT_TODO: nutrition estimation user prompt]\n"
            f"<recipe_id>{recipe.id}</recipe_id>\n"
            f"<name>{recipe.name}</name>\n"
            f"<description>{recipe.description or ''}</description>\n"
            f"<servings>{recipe.servings}</servings>\n"
            f"<ingredients>{ingredient_lines}</ingredients>\n"
            f"<steps>{recipe.steps}</steps>"
        )
        model = route_model(AgentTask.NUTRITIONAL_PROFILE)
        message = await self._client.complete(
            [{"role": "user", "content": user}],
            model=model,
            tools=[_OUTPUT_NUTRITION_TOOL],
            tool_choice={"type": "tool", "name": "output_nutrition"},
            max_tokens=1024,
            system=system,
            trace_id=trace_id,
            user_id=recipe.user_id,
            job_id=job_id,
            task=AgentTask.NUTRITIONAL_PROFILE.value,
        )
        for block in message.content:
            if block.type == "tool_use" and block.name == "output_nutrition":
                data = dict(block.input or {})
                draft = RecipeNutritionDraft(
                    calories_per_serving=Decimal(str(data["calories_per_serving"])),
                    protein_g=Decimal(str(data["protein_g"])),
                    carbs_g=Decimal(str(data["carbs_g"])),
                    fat_g=Decimal(str(data["fat_g"])),
                    fiber_g=Decimal(str(data["fiber_g"])),
                    sat_fat_g=(
                        Decimal(str(data["sat_fat_g"]))
                        if data.get("sat_fat_g") is not None
                        else None
                    ),
                    sugar_g=(
                        Decimal(str(data["sugar_g"]))
                        if data.get("sugar_g") is not None
                        else None
                    ),
                    nutritional_highlights=list(
                        data.get("nutritional_highlights") or []
                    ),
                )
                try:
                    self._nutrition.check(
                        NutritionPerServing(
                            calories_kcal=float(draft.calories_per_serving),
                            protein_g=float(draft.protein_g),
                            fat_g=float(draft.fat_g),
                            carbohydrates_g=float(draft.carbs_g),
                            fiber_g=float(draft.fiber_g),
                        )
                    )
                except NutritionOutOfRangeError as exc:
                    logger.warning(
                        "nutrition_estimate_out_of_range",
                        recipe_id=str(recipe.id),
                        field=exc.field,
                        value=exc.value,
                        trace_id=trace_id,
                    )
                return draft
        raise ValueError(f"No nutrition tool output for recipe {recipe.id}")
