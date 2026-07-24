"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export function useCalendarWeeks(params?: { from?: string; to?: string }) {
  return useQuery({
    queryKey: ["calendar", params ?? {}],
    queryFn: () => apiClient.listCalendarWeeks(params),
  });
}

export function useCalendarWeek(weekStartDate: string | undefined) {
  return useQuery({
    queryKey: ["calendar", weekStartDate],
    queryFn: () => {
      if (!weekStartDate) throw new Error("weekStartDate required");
      return apiClient.getCalendarWeek(weekStartDate);
    },
    enabled: Boolean(weekStartDate),
  });
}
