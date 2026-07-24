"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export function useShoppingList(planId: string | undefined) {
  return useQuery({
    queryKey: ["shopping-list", planId],
    queryFn: () => {
      if (!planId) {
        throw new Error("planId is required");
      }
      return apiClient.getShoppingList(planId);
    },
    enabled: Boolean(planId),
  });
}
