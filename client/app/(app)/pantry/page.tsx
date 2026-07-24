"use client";

import { useMemo, useState } from "react";
import { PantryAddBar } from "@/components/pantry/PantryAddBar";
import { PantryCategoryLabel } from "@/components/pantry/PantryCategoryLabel";
import { PantryItemCard } from "@/components/pantry/PantryItemCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageShell } from "@/components/shared/PageShell";
import { TierGateWrapper } from "@/components/shared/TierGateWrapper";
import { Skeleton } from "@/components/ui/skeleton";
import { useAddPantryItem, useDeletePantryItem, usePantry } from "@/hooks";
import type { PantryItem } from "@/lib/types";

function guessCategory(name: string): string {
  const n = name.toLowerCase();
  if (
    /spinach|avocado|cucumber|lettuce|tomato|berry|fruit|vegetable|produce/.test(
      n,
    )
  ) {
    return "Produce";
  }
  if (/nut|seed|almond|cashew|chia|hemp|walnut/.test(n)) {
    return "Nuts & Seeds";
  }
  return "Pantry Staples";
}

function groupPantry(items: PantryItem[]) {
  const groups = new Map<string, PantryItem[]>();
  for (const item of items) {
    const key = guessCategory(item.ingredient_name_raw);
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  }
  return Array.from(groups.entries());
}

export default function PantryPage() {
  const { data, isLoading, isError } = usePantry({ limit: 100 });
  const addMutation = useAddPantryItem();
  const deleteMutation = useDeletePantryItem();
  const [draft, setDraft] = useState("");

  const groups = useMemo(
    () => groupPantry(data?.data ?? []),
    [data?.data],
  );

  async function handleAdd() {
    const name = draft.trim();
    if (!name) return;
    await addMutation.mutateAsync({ ingredient_name_raw: name });
    setDraft("");
  }

  const count = data?.pagination.total ?? data?.data.length ?? 0;

  return (
    <TierGateWrapper requiredTier="paid">
      <PageShell>
        <PageHeader
          eyebrow="Pantry"
          title="What you have."
          description={`${count} ingredients on hand`}
        />

        <PantryAddBar
          value={draft}
          onChange={setDraft}
          onSubmit={() => void handleAdd()}
          disabled={addMutation.isPending}
          className="mb-8"
        />

        {isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : null}

        {isError ? (
          <p className="font-sans text-body text-cta">Could not load pantry.</p>
        ) : null}

        {!isLoading
          ? groups.map(([category, items]) => (
              <div key={category}>
                <PantryCategoryLabel category={category} />
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {items.map((item) => (
                    <PantryItemCard
                      key={item.id}
                      item={item}
                      category={category}
                      onRemove={() =>
                        void deleteMutation.mutateAsync(item.id)
                      }
                    />
                  ))}
                </div>
              </div>
            ))
          : null}

        {!isLoading && groups.length === 0 ? (
          <p className="font-sans text-body-sm italic text-text-muted">
            Your pantry is empty — add ingredients above.
          </p>
        ) : null}
      </PageShell>
    </TierGateWrapper>
  );
}
