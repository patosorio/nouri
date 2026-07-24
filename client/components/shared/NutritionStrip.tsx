import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface NutritionStripProps {
  title?: string;
  calories: number;
  proteinG: number;
  carbsG: number;
  fatG?: number;
  fiberG?: number;
  /** Prefix stat labels with "Avg " (weekly strip on meal planner). */
  avgLabels?: boolean;
  compact?: boolean;
  vertical?: boolean;
  className?: string;
  footer?: ReactNode;
  trailing?: ReactNode;
}

function formatNum(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(0);
}

export function NutritionStrip({
  title,
  calories,
  proteinG,
  carbsG,
  fatG,
  fiberG,
  avgLabels = false,
  compact = false,
  vertical = false,
  className,
  footer,
  trailing,
}: NutritionStripProps) {
  const prefix = avgLabels ? "Avg " : "";
  const stats: { value: string; label: string }[] = [
    { value: formatNum(calories), label: `${prefix}Calories` },
    { value: `${formatNum(proteinG)}g`, label: `${prefix}Protein` },
    {
      value: `${formatNum(carbsG)}g`,
      label: vertical ? `${prefix}Carbohydrates` : `${prefix}Carbs`,
    },
  ];
  if (fatG != null) {
    stats.push({ value: `${formatNum(fatG)}g`, label: `${prefix}Fat` });
  }
  if (fiberG != null) {
    stats.push({ value: `${formatNum(fiberG)}g`, label: `${prefix}Fiber` });
  }

  return (
    <div
      className={cn(
        "rounded-card bg-primary-dark text-white",
        compact ? "px-[18px] py-4" : "px-7 py-[22px]",
        trailing
          ? "flex flex-wrap items-center justify-between gap-4"
          : null,
        className,
      )}
    >
      <div className="min-w-0 flex-1">
        {title ? (
          <p className="mb-3 font-mono text-eyebrow-sm uppercase tracking-[0.15em] text-neutral">
            {title}
          </p>
        ) : null}
        {vertical ? (
          <div className="flex flex-col gap-2.5">
            {stats.map((stat) => (
              <div
                key={stat.label}
                className="flex items-center justify-between font-mono text-[13px]"
              >
                <span className="text-white/70">{stat.label}</span>
                <strong className="text-title font-medium text-highlight">
                  {stat.label.includes("Calories")
                    ? `${stat.value} kcal`
                    : stat.value}
                </strong>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-wrap gap-x-7 gap-y-2">
            {stats.map((stat) => (
              <div key={stat.label} className="flex flex-col gap-0.5">
                <span className="font-mono text-title text-highlight">
                  {stat.value}
                </span>
                <span className="font-mono text-label uppercase tracking-[0.1em] text-white/60">
                  {stat.label}
                </span>
              </div>
            ))}
          </div>
        )}
        {footer}
      </div>
      {trailing}
    </div>
  );
}
