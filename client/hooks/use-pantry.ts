"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { PantryItemPayload } from "@/lib/types";

export function usePantry(params?: { offset?: number; limit?: number }) {
  return useQuery({
    queryKey: ["pantry", params ?? {}],
    queryFn: () => apiClient.listPantryItems(params),
  });
}

export function useAddPantryItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: PantryItemPayload) => apiClient.addPantryItem(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pantry"] });
    },
  });
}

export function useDeletePantryItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: string) => apiClient.deletePantryItem(itemId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pantry"] });
    },
  });
}
