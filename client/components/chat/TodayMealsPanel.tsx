import Link from "next/link";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { NutritionStrip } from "@/components/shared/NutritionStrip";
import { RawCookedTag } from "@/components/shared/RawCookedTag";
import { toRawCookedTag } from "@/lib/cooking";
import type { PlanItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface TodayMealsPanelProps {
  items: PlanItem[];
  planId?: string | null;
  weekTitle?: string | null;
  weekCalories?: number | null;
  weekProteinG?: number | null;
  weekCarbsG?: number | null;
  weekFatG?: number | null;
  className?: string;
}

export function TodayMealsPanel({
  items,
  planId,
  weekTitle,
  weekCalories,
  weekProteinG,
  weekCarbsG,
  weekFatG,
  className,
}: TodayMealsPanelProps) {
  const hasWeekNutrition =
    weekCalories != null &&
    weekProteinG != null &&
    weekCarbsG != null;

  return (
    <div className={cn("flex h-full flex-col gap-4", className)}>
      <EyebrowLabel>This Week</EyebrowLabel>

      {hasWeekNutrition ? (
        <NutritionStrip
          compact
          title={weekTitle ?? "Weekly nutrition"}
          calories={weekCalories}
          proteinG={weekProteinG}
          carbsG={weekCarbsG}
          fatG={weekFatG ?? undefined}
        />
      ) : (
        <p className="font-sans text-body-sm italic text-text-muted">
          No active plan nutrition yet.
        </p>
      )}

      <Link href={planId ? `/plans/${planId}` : "/plans"} className="btn-primary w-full">
        Generate New Plan
      </Link>

      <EyebrowLabel className="mt-2">Today&apos;s Meals</EyebrowLabel>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto">
        {items.length === 0 ? (
          <p className="font-sans text-body-sm italic text-text-muted">
            No meals scheduled for today yet.
          </p>
        ) : (
          items.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface px-3.5 py-2.5"
            >
              <p className="min-w-0 truncate font-sans text-body font-medium text-text">
                {item.name}
              </p>
              {item.slot !== "juice" ? (
                <RawCookedTag type={toRawCookedTag(item.prep_method)} />
              ) : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
