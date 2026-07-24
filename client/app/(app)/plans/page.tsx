"use client";

import { PlanListCard } from "@/components/plans/PlanListCard";
import { PlansListActions } from "@/components/plans/PlanDetailView";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageShell } from "@/components/shared/PageShell";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlans } from "@/hooks";

export default function PlansPage() {
  const { data, isLoading, isError } = usePlans();

  return (
    <PageShell>
      <PageHeader
        eyebrow="Library"
        title="Meal plans"
        description="Review, approve, and schedule your generated weeks."
        actions={<PlansListActions />}
      />

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      ) : null}

      {isError ? (
        <p className="font-sans text-body text-cta">Could not load plans.</p>
      ) : null}

      {data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.data.map((plan) => (
            <PlanListCard key={plan.id} plan={plan} />
          ))}
          {data.data.length === 0 ? (
            <p className="font-sans text-body-sm italic text-text-muted">
              No plans yet — generate your first week.
            </p>
          ) : null}
        </div>
      ) : null}
    </PageShell>
  );
}
