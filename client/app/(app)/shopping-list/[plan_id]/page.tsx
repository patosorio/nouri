"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { PantrySummaryPanel } from "@/components/shopping/PantrySummaryPanel";
import { PurchasedDisclosure } from "@/components/shopping/PurchasedDisclosure";
import { ShoppingCategoryLabel } from "@/components/shopping/ShoppingCategoryLabel";
import { ShoppingItemRow } from "@/components/shopping/ShoppingItemRow";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageShell } from "@/components/shared/PageShell";
import { Skeleton } from "@/components/ui/skeleton";
import { usePantry, useShoppingList } from "@/hooks";
import type { ShoppingListItem } from "@/lib/types";

function groupByCategory(items: ShoppingListItem[]) {
  const groups = new Map<string, ShoppingListItem[]>();
  for (const item of items) {
    const key = item.category?.trim() || "Other";
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  }
  return Array.from(groups.entries());
}

export default function ShoppingListByPlanPage() {
  const params = useParams<{ plan_id: string }>();
  const planId = params.plan_id;
  const { data, isLoading, isError } = useShoppingList(planId);
  const { data: pantryData } = usePantry({ limit: 50 });
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [showPurchased, setShowPurchased] = useState(false);

  useEffect(() => {
    if (!data) return;
    setCheckedIds(
      new Set(data.items.filter((i) => i.is_checked).map((i) => i.id)),
    );
  }, [data]);

  const unchecked = useMemo(
    () => (data?.items ?? []).filter((i) => !checkedIds.has(i.id)),
    [data, checkedIds],
  );
  const purchased = useMemo(
    () => (data?.items ?? []).filter((i) => checkedIds.has(i.id)),
    [data, checkedIds],
  );

  function toggle(id: string) {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (isLoading) {
    return (
      <PageShell>
        <Skeleton className="mb-4 h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell>
        <p className="font-sans text-body text-cta">
          Shopping list unavailable for this plan.
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow="Shopping"
        title="Shopping List"
        description={`${data.items.length} items${
          purchased.length > 0 ? ` · ${purchased.length} checked` : ""
        }`}
        actions={
          <button type="button" className="btn-ghost">
            Export List
          </button>
        }
      />

      <div className="flex flex-col gap-8 lg:flex-row">
        <div className="min-w-0 flex-1">
          {groupByCategory(unchecked).map(([category, items]) => (
            <div key={category} className="mb-7">
              <ShoppingCategoryLabel category={category} />
              <div className="rounded-card border border-border bg-surface px-4 py-1">
                {items.map((item) => (
                  <ShoppingItemRow
                    key={item.id}
                    item={item}
                    checked={false}
                    onToggle={() => toggle(item.id)}
                  />
                ))}
              </div>
            </div>
          ))}

          {purchased.length > 0 ? (
            <div>
              <PurchasedDisclosure
                count={purchased.length}
                expanded={showPurchased}
                onToggle={() => setShowPurchased((v) => !v)}
              />
              {showPurchased ? (
                <div className="mt-2 rounded-card border border-border bg-surface px-4 py-1">
                  {purchased.map((item) => (
                    <ShoppingItemRow
                      key={item.id}
                      item={item}
                      checked
                      onToggle={() => toggle(item.id)}
                    />
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {unchecked.length === 0 && purchased.length === 0 ? (
            <p className="font-sans text-body-sm italic text-text-muted">
              No shopping items for this plan yet.
            </p>
          ) : null}
        </div>

        <PantrySummaryPanel items={pantryData?.data ?? []} />
      </div>
    </PageShell>
  );
}
