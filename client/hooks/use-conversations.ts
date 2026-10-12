"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export function useConversations(params?: { offset?: number; limit?: number }) {
  return useQuery({
    queryKey: ["conversations", params ?? {}],
    queryFn: () => apiClient.listConversations(params),
  });
}

export function useConversation(conversationId: string | undefined) {
  return useQuery({
    queryKey: ["conversations", conversationId],
    queryFn: () => {
      if (!conversationId) {
        throw new Error("conversationId is required");
      }
      return apiClient.getConversation(conversationId);
    },
    enabled: Boolean(conversationId),
  });
}
