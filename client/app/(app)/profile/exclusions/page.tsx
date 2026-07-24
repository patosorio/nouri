"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExclusionTag } from "@/components/profile/ExclusionTag";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient } from "@/lib/api-client";

export default function ProfileExclusionsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["exclusions"],
    queryFn: () => apiClient.listExclusions(),
  });
  const [draft, setDraft] = useState("");

  const addMutation = useMutation({
    mutationFn: (name: string) =>
      apiClient.addExclusion({ ingredient_name_raw: name }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["exclusions"] });
      setDraft("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.deleteExclusion(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["exclusions"] });
    },
  });

  return (
    <section>
      <EyebrowLabel>Exclusions</EyebrowLabel>
      <h2 className="mt-2 mb-2 font-sans text-title font-semibold text-text">
        Ingredients to avoid
      </h2>
      <p className="mb-6 max-w-md font-sans italic text-text-muted">
        These never appear in your plans or recipe suggestions.
      </p>

      {isLoading ? <Skeleton className="h-24 w-full max-w-md" /> : null}

      <div className="mb-6 flex flex-wrap gap-2">
        {(data?.data ?? []).map((item) => (
          <ExclusionTag
            key={item.id}
            name={item.ingredient_name_raw}
            onRemove={() => void deleteMutation.mutateAsync(item.id)}
          />
        ))}
        {!isLoading && (data?.data.length ?? 0) === 0 ? (
          <p className="font-sans text-body-sm italic text-text-muted">
            No exclusions yet.
          </p>
        ) : null}
      </div>

      <form
        className="flex max-w-md gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) void addMutation.mutateAsync(draft.trim());
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="e.g. peanuts"
          className="flex-1 rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none focus:border-primary"
        />
        <button
          type="submit"
          disabled={addMutation.isPending || !draft.trim()}
          className="btn-primary"
        >
          Add
        </button>
      </form>
    </section>
  );
}
