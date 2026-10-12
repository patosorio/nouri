import type { PlanGenerationProgress } from "@/lib/types";
import { cn } from "@/lib/utils";

const STAGE_LABEL: Record<string, string> = {
  queued: "Queued",
  finding_recipes: "Finding recipes",
  generating_week: "Writing the week",
  assigning_slots: "Fitting meals to your targets",
  saving: "Saving recipes",
  writing_days: "Filling days",
};

interface GenerationProgressBarProps {
  generation: PlanGenerationProgress | null | undefined;
  numDays: number;
  className?: string;
}

export function isGenerationInFlight(
  generation: PlanGenerationProgress | null | undefined,
): boolean {
  return generation?.status === "pending" || generation?.status === "running";
}

export function GenerationProgressBar({
  generation,
  numDays,
  className,
}: GenerationProgressBarProps) {
  if (!generation) return null;

  if (generation.status === "failed") {
    return (
      <p className={cn("mt-3 font-sans text-body-sm text-cta", className)}>
        Generation failed
        {generation.error_message ? ` — ${generation.error_message}` : ""}.
      </p>
    );
  }

  if (!isGenerationInFlight(generation)) {
    return null;
  }

  const pct = Math.max(4, Math.min(100, generation.progress_pct));
  const daysDone = generation.days_completed;
  const daysTotal = generation.days_total || numDays;
  const stage =
    (generation.stage && STAGE_LABEL[generation.stage]) || "Creating…";

  return (
    <div className={cn("mt-4", className)}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <p className="m-0 font-mono text-[10px] uppercase tracking-[0.08em] text-primary">
          {stage}
        </p>
        <p className="m-0 font-mono text-[10px] uppercase tracking-[0.08em] text-text-muted">
          {daysDone > 0
            ? `Day ${daysDone} of ${daysTotal}`
            : `${pct}%`}
        </p>
      </div>
      <div className="h-1.5 overflow-hidden rounded-pill bg-primary/15">
        <div
          className="h-full rounded-pill bg-primary transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="m-0 mt-1.5 font-sans text-[0.8rem] italic text-text-muted">
        Usually a few minutes. You can leave this page.
      </p>
    </div>
  );
}
