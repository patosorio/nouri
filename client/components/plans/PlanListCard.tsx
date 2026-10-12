"use client";

import { useState } from "react";
import Link from "next/link";
import { Archive } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import {
  GenerationProgressBar,
  isGenerationInFlight,
} from "@/components/plans/GenerationProgressBar";
import { useDeletePlan } from "@/hooks";
import { ApiError } from "@/lib/api-client";
import type { MealPlanSummary, PlanStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface PlanListCardProps {
  plan: MealPlanSummary;
  className?: string;
}

const STATUS_LABEL: Record<PlanStatus, string> = {
  draft: "Draft",
  reviewing: "Reviewing",
  approved: "Approved",
};

export function PlanListCard({ plan, className }: PlanListCardProps) {
  const deletePlan = useDeletePlan();
  const [error, setError] = useState<string | null>(null);
  const generating = isGenerationInFlight(plan.generation);
  const failed = plan.generation?.status === "failed";
  const badgeLabel = generating
    ? "Creating"
    : failed
      ? "Failed"
      : STATUS_LABEL[plan.status];
  const archiving = deletePlan.isPending;

  async function handleArchive() {
    setError(null);
    try {
      await deletePlan.mutateAsync(plan.id);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Could not archive this plan.");
      }
    }
  }

  return (
    <article
      className={cn(
        "relative rounded-card border border-border bg-card transition-colors hover:border-primary/40",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3 px-5 pt-5">
        <Link href={`/plans/${plan.id}`} className="min-w-0 flex-1 no-underline">
          <EyebrowLabel size="sm">
            {plan.week_start_date}
            {plan.scheduled_date ? ` · scheduled ${plan.scheduled_date}` : ""}
          </EyebrowLabel>
          <h2 className="mt-2 font-sans text-title font-medium text-text">
            {plan.title ?? `${plan.num_days}-day plan`}
          </h2>
        </Link>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge
            variant="secondary"
            className={
              generating
                ? "bg-primary/10 text-primary"
                : failed
                  ? "bg-cta/10 text-cta"
                  : undefined
            }
          >
            {badgeLabel}
          </Badge>
          <button
            type="button"
            onClick={() => void handleArchive()}
            disabled={archiving}
            aria-label="Archive plan"
            title="Archive plan"
            className="flex size-8 items-center justify-center rounded-card text-text-muted transition-colors hover:bg-primary/8 hover:text-text disabled:opacity-50"
          >
            <Archive className="size-4" aria-hidden />
          </button>
        </div>
      </div>
      <Link href={`/plans/${plan.id}`} className="block px-5 pb-5 no-underline">
        <p className="mt-3 font-mono text-eyebrow-sm uppercase text-text-muted">
          {plan.num_days} days
        </p>
        <GenerationProgressBar
          generation={plan.generation}
          numDays={plan.num_days}
        />
      </Link>
      {error ? (
        <p className="px-5 pb-4 font-sans text-body-sm text-cta">{error}</p>
      ) : null}
    </article>
  );
}
