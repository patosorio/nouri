"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { PlanStatus } from "@/lib/types";

function hasActiveGeneration(
  data:
    | { data: { generation?: { status: string } | null }[] }
    | undefined,
): boolean {
  return Boolean(
    data?.data.some(
      (plan) =>
        plan.generation?.status === "pending" ||
        plan.generation?.status === "running",
    ),
  );
}

export function usePlans(params?: {
  offset?: number;
  limit?: number;
  status?: PlanStatus;
}) {
  return useQuery({
    queryKey: ["plans", params ?? {}],
    queryFn: () => apiClient.listPlans(params),
    refetchInterval: (query) =>
      hasActiveGeneration(query.state.data) ? 2500 : false,
  });
}

export function usePlan(planId: string | undefined) {
  return useQuery({
    queryKey: ["plans", planId],
    queryFn: () => {
      if (!planId) {
        throw new Error("planId is required");
      }
      return apiClient.getPlan(planId);
    },
    enabled: Boolean(planId),
    refetchInterval: (query) => {
      const generation = query.state.data?.generation;
      if (
        generation?.status === "pending" ||
        generation?.status === "running"
      ) {
        return 2500;
      }
      return false;
    },
  });
}

export function useDeletePlan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (planId: string) => apiClient.deletePlan(planId),
    onSuccess: (_data, planId) => {
      void queryClient.invalidateQueries({ queryKey: ["plans"] });
      void queryClient.removeQueries({ queryKey: ["plans", planId] });
    },
  });
}
