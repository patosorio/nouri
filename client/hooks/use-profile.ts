"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { ProfileUpdatePayload } from "@/lib/types";

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: () => apiClient.getProfile(),
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: ProfileUpdatePayload) => apiClient.updateProfile(body),
    onSuccess: (profile) => {
      queryClient.setQueryData(["profile"], profile);
    },
  });
}
