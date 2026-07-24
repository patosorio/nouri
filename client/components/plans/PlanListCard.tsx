import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
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
  return (
    <Link
      href={`/plans/${plan.id}`}
      className={cn(
        "block rounded-card border border-border bg-card p-5 transition-colors hover:border-brand-primary/40",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <EyebrowLabel size="sm">
            {plan.week_start_date}
            {plan.scheduled_date ? ` · scheduled ${plan.scheduled_date}` : ""}
          </EyebrowLabel>
          <h2 className="mt-2 font-sans text-title font-medium text-text-primary">
            {plan.title ?? `${plan.num_days}-day plan`}
          </h2>
        </div>
        <Badge variant="secondary">{STATUS_LABEL[plan.status]}</Badge>
      </div>
      <p className="mt-3 font-mono text-eyebrow-sm uppercase text-muted-foreground">
        {plan.num_days} days
      </p>
    </Link>
  );
}
