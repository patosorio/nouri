import Link from "next/link";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { cn } from "@/lib/utils";

interface WeekDetailsPanelProps {
  planName: string;
  dateRange: string;
  planId: string | null;
  avgCalories?: number | null;
  avgProteinG?: number | null;
  className?: string;
  empty?: boolean;
}

export function WeekDetailsPanel({
  planName,
  dateRange,
  planId,
  avgCalories,
  avgProteinG,
  className,
  empty = false,
}: WeekDetailsPanelProps) {
  return (
    <aside
      className={cn(
        "w-full shrink-0 self-start rounded-card border border-border bg-surface p-6 lg:w-80",
        className,
      )}
    >
      <EyebrowLabel>Week Details</EyebrowLabel>

      {empty ? (
        <p className="mt-3 font-sans text-body-sm italic text-text-muted">
          Select a week with an assigned plan to see details.
        </p>
      ) : (
        <>
          <p className="mt-1.5 mb-0.5 font-sans text-title font-semibold text-text">
            {planName}
          </p>
          <p className="m-0 font-mono text-[11px] text-text-muted">{dateRange}</p>

          {avgCalories != null ? (
            <div className="my-4 rounded-card bg-primary-dark px-5 py-[18px] text-white">
              <div className="flex flex-wrap gap-[18px]">
                <div className="flex flex-col gap-0.5">
                  <span className="font-mono text-title text-highlight">
                    {Math.round(avgCalories).toLocaleString()}
                  </span>
                  <span className="font-mono text-label uppercase tracking-[0.1em] text-white/60">
                    Avg Kcal
                  </span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="font-mono text-title text-highlight">
                    {Math.round(avgProteinG ?? 0)}g
                  </span>
                  <span className="font-mono text-label uppercase tracking-[0.1em] text-white/60">
                    Protein
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="my-4" />
          )}

          {planId ? (
            <div className="flex flex-col gap-2.5">
              <Link
                href={`/plans/${planId}`}
                className="btn-primary w-full"
              >
                View Full Plan
              </Link>
              <Link
                href={`/plans/${planId}`}
                className="btn-ghost w-full"
              >
                Clone to New Week
              </Link>
            </div>
          ) : null}
        </>
      )}
    </aside>
  );
}
