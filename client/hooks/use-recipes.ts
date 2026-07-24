"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { RecipeFilters } from "@/lib/types";

export function useRecipes(filters?: RecipeFilters) {
  const hasQuery = Boolean(filters?.q?.trim());

  return useQuery({
    queryKey: ["recipes", filters ?? {}],
    queryFn: () =>
      hasQuery
        ? apiClient.searchRecipes(filters)
        : apiClient.listRecipes(filters),
  });
}

export function useRecipe(recipeId: string | undefined) {
  return useQuery({
    queryKey: ["recipes", recipeId],
    queryFn: () => {
      if (!recipeId) {
        throw new Error("recipeId is required");
      }
      return apiClient.getRecipe(recipeId);
    },
    enabled: Boolean(recipeId),
  });
}
