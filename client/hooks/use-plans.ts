"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { PlanStatus } from "@/lib/types";

export function usePlans(params?: {
  offset?: number;
  limit?: number;
  status?: PlanStatus;
}) {
  return useQuery({
    queryKey: ["plans", params ?? {}],
    queryFn: () => apiClient.listPlans(params),
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
  });
}
