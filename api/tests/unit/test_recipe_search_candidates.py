"""Planning retrieval does not call Voyage, even for a large library."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from search.recipe_search_service import RecipeSearchService


@pytest.mark.asyncio
async def test_find_candidates_delegates_without_embeddings() -> None:
    search = RecipeSearchService(voyage_client=object())
    search.embed_texts = AsyncMock(side_effect=AssertionError("planning must not embed"))  # type: ignore[method-assign]
    search.planning_candidates = AsyncMock(return_value=[])  # type: ignore[method-assign]

    result = await search.find_candidates(uuid4(), "plant_based", 7, AsyncMock())

    assert result == []
    search.embed_texts.assert_not_called()
    search.planning_candidates.assert_awaited()
