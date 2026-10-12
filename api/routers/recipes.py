"""Recipe routes — docs/4_API_DESIGN.yaml /recipes*."""

from __future__ import annotations

import base64
from typing import Any
from uuid import UUID

from agent.recipe_generator import RecipeGeneratorAgent
from agent.recipe_importer import RecipeImporterAgent
from db.models import (
    CookingType,
    DietType,
    PreparationType,
    RecipeDietCompatibility,
    RecipeIngredient,
    RecipeNutrition,
    RecipeType,
)
from dependencies import CurrentUser, get_current_user, get_db
from exceptions import NotFoundError, TierGateError
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
from schemas.agent import RecipeDraft as AgentRecipeDraft
from schemas.agent import RecipeGenerationRequest
from schemas.http import RecipeExpandPayload, RecipeSavePayload
from schemas.recipes import RecipeFilters, RecipeUpdate
from search.embedding_jobs import embed_recipe_by_id
from search.recipe_search_service import RecipeSearchService
from services.recipe_service import RecipeService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routers.serializers import (
    pagination_meta,
    serialize_recipe,
    serialize_recipe_list_item,
)

router = APIRouter()
_service = RecipeService()
_current_user = Depends(get_current_user)
_db = Depends(get_db)
_offset = Query(0, ge=0)
_limit = Query(30, ge=1, le=30)
_optional_file = File(None)


def _agent_draft_to_api(draft: AgentRecipeDraft) -> dict[str, Any]:
    """Map tech-spec AI RecipeDraft → OpenAPI RecipeDraft field names."""
    cook_minutes = None
    if draft.total_time_minutes is not None and draft.prep_time_minutes is not None:
        cook_minutes = max(0, draft.total_time_minutes - draft.prep_time_minutes)
    nutrition = None
    if draft.nutrition_per_serving is not None:
        n = draft.nutrition_per_serving
        nutrition = {
            "calories_per_serving": n.calories_kcal,
            "protein_g": n.protein_g,
            "carbs_g": n.carbohydrates_g,
            "fat_g": n.fat_g,
            "fiber_g": n.fiber_g,
            "sugar_g": n.sugar_g,
            "nutritional_highlights": [],
            "food_advisor_notes": None,
        }
    return {
        "name": draft.title,
        "description": draft.description,
        "servings": draft.servings,
        "prep_minutes": draft.prep_time_minutes,
        "cook_minutes": cook_minutes,
        "recipe_type": "juice" if draft.is_juicing else "meal",
        "diet_types": [draft.diet_type.value],
        "diet_subtypes": [],
        "cooking_type": "cooked_100",
        "cuisine": [],
        "tags": [],
        "prep_method": draft.prep_type.value if draft.prep_type else None,
        "color": None,
        "source": "ai_generated",
        "ingredients": [
            {
                "ingredient_id": str(i.ingredient_id) if i.ingredient_id else None,
                "ingredient_name": i.ingredient_name,
                "amount": float(i.quantity),
                "unit": i.unit,
                "notes": i.notes,
            }
            for i in draft.ingredients
        ],
        "steps": [
            {
                "step_number": s.step_number,
                "instruction": s.instruction,
                "duration_minutes": s.duration_minutes,
                "tips": s.tips,
            }
            for s in draft.steps
        ],
        "nutrition": nutrition,
        "import_source_hint": None,
    }


async def _load_recipe_response(
    recipe_id: UUID, user_id: UUID, db: AsyncSession
) -> dict[str, Any]:
    recipe = await _service.get_recipe(recipe_id, user_id, db)
    ing_result = await db.execute(
        select(RecipeIngredient)
        .where(RecipeIngredient.recipe_id == recipe.id)
        .order_by(RecipeIngredient.sort_order.asc())
    )
    ingredients = []
    for row in ing_result.scalars().all():
        ingredients.append(
            {
                "id": str(row.id),
                "ingredient_id": str(row.ingredient_id),
                "ingredient_name": None,
                "amount": float(row.amount),
                "unit": row.unit,
                "notes": row.notes,
                "is_optional": row.is_optional,
                "sort_order": row.sort_order,
            }
        )
    diet_result = await db.execute(
        select(RecipeDietCompatibility).where(
            RecipeDietCompatibility.recipe_id == recipe.id
        )
    )
    diet_types = [r.diet_type.value for r in diet_result.scalars().all()]
    nutrition_row = await db.get(RecipeNutrition, recipe.id)
    nutrition = None
    if nutrition_row is not None:
        from routers.serializers import serialize_nutrition

        nutrition = serialize_nutrition(nutrition_row, include_pro_fields=True)
    return serialize_recipe(
        recipe,
        ingredients=ingredients,
        nutrition=nutrition,
        diet_types=diet_types,
    )


@router.get("/recipes")
async def list_recipes(
    offset: int = _offset,
    limit: int = _limit,
    recipe_type: RecipeType | None = None,
    prep_method: PreparationType | None = None,
    cooking_type: CookingType | None = None,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    filters = RecipeFilters(
        recipe_type=recipe_type,
        prep_method=prep_method,
        cooking_type=cooking_type,
        offset=offset,
        limit=limit,
    )
    page = await _service.list_recipes(current_user.id, filters, db)
    return {
        "data": [serialize_recipe_list_item(r) for r in page.data],
        "pagination": pagination_meta(page.total, page.offset, page.limit),
    }


@router.get("/recipes/search")
async def search_recipes(
    q: str | None = None,
    offset: int = _offset,
    limit: int = _limit,
    recipe_type: RecipeType | None = None,
    prep_method: PreparationType | None = None,
    cooking_type: CookingType | None = None,
    diet_type: DietType | None = None,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    filters = RecipeFilters(
        q=q,
        recipe_type=recipe_type,
        prep_method=prep_method,
        cooking_type=cooking_type,
        diet_type=diet_type,
        offset=offset,
        limit=limit,
    )
    page = await RecipeSearchService().search(
        current_user.id, q or "", filters, db
    )
    return {
        "data": [serialize_recipe_list_item(r) for r in page.data],
        "pagination": pagination_meta(page.total, page.offset, page.limit),
    }


@router.post("/recipes", status_code=status.HTTP_201_CREATED)
async def save_recipe(
    body: RecipeSavePayload,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    recipe = await _service.save_recipe(current_user.id, body.draft, db)
    background_tasks.add_task(embed_recipe_by_id, recipe.id)
    return await _load_recipe_response(recipe.id, current_user.id, db)


@router.post("/recipes/import")
async def import_recipe(
    text: str | None = Form(None),
    file: UploadFile | None = _optional_file,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    importer = RecipeImporterAgent()
    if file is not None and file.filename:
        if current_user.tier != "pro":
            raise TierGateError("Image/PDF import requires a pro plan")
        raw = await file.read()
        media_type = file.content_type or "image/jpeg"
        draft = await _import_from_bytes(
            importer, current_user.id, raw, media_type, db
        )
    elif text:
        draft = await importer.import_from_text(current_user.id, text, db)
    else:
        raise NotFoundError("Provide text or file")
    return _agent_draft_to_api(draft)


async def _import_from_bytes(
    importer: RecipeImporterAgent,
    user_id: UUID,
    raw: bytes,
    media_type: str,
    db: AsyncSession,
) -> AgentRecipeDraft:
    """Vision import via base64 content block (no object-storage URL yet)."""
    from config import AgentTask, route_model

    exclusion_constraint = await importer._exclusion_constraint(user_id, db)
    system_prompt = (
        "You are Nouri's recipe import engine. Extract the complete recipe "
        "exactly as shown in the attached image or PDF — do not invent, infer, "
        "or embellish any ingredient, quantity, or step that isn't visibly "
        "present in the source. If a quantity or step is illegible or missing, "
        "represent it as best you can from what's visible and note the gap in "
        "notes rather than guessing a specific number. If an ingredient in the "
        "source is on this user's exclusion list, extract it faithfully anyway "
        "— accuracy of the source comes first — but flag the conflict in notes "
        "so the user is warned before saving. Call output_recipe once with the "
        "extracted recipe.\n"
    )
    b64 = base64.b64encode(raw).decode("ascii")
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64,
            },
        },
        {
            "type": "text",
            "text": (
                "<exclusion_constraints>"
                f"{exclusion_constraint}"
                "</exclusion_constraints>\n"
                "Extract the complete recipe from this image. Include every "
                "ingredient with its quantity and unit, and every step in order."
            ),
        },
    ]
    draft = await importer._call_and_parse(
        system_prompt=system_prompt,
        user_content=content,
        model=route_model(AgentTask.RECIPE_IMPORT_IMAGE),
    )
    return await importer._postprocess(draft, db)


@router.get("/recipes/{recipe_id}")
async def get_recipe(
    recipe_id: UUID,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    return await _load_recipe_response(recipe_id, current_user.id, db)


@router.patch("/recipes/{recipe_id}")
async def update_recipe(
    recipe_id: UUID,
    body: RecipeUpdate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    await _service.update_recipe(recipe_id, current_user.id, body, db)
    background_tasks.add_task(embed_recipe_by_id, recipe_id)
    return await _load_recipe_response(recipe_id, current_user.id, db)


@router.delete(
    "/recipes/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_recipe(
    recipe_id: UUID,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> Response:
    await _service.delete_recipe(recipe_id, current_user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/recipes/{recipe_id}/expand")
async def expand_recipe(
    recipe_id: UUID,
    body: RecipeExpandPayload,
    current_user: CurrentUser = _current_user,
    db: AsyncSession = _db,
) -> dict[str, object]:
    await _service.get_recipe(recipe_id, current_user.id, db)
    draft = await RecipeGeneratorAgent().generate(
        current_user.id,
        RecipeGenerationRequest(
            description=body.instruction,
            recipe_id=recipe_id,
        ),
        db,
    )
    return _agent_draft_to_api(draft)
