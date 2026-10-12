"use client";

import Link from "next/link";
import { History } from "lucide-react";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { DisclaimerBanner } from "@/components/shared/DisclaimerBanner";
import { NutritionStrip } from "@/components/shared/NutritionStrip";
import { RawCookedTag } from "@/components/shared/RawCookedTag";
import { toRawCookedTag } from "@/lib/cooking";
import type { PlanGenerationProgress, PlanItem } from "@/lib/types";
import {
  GenerationProgressBar,
  isGenerationInFlight,
} from "@/components/plans/GenerationProgressBar";
import { cn } from "@/lib/utils";

interface TodayMealsPanelProps {
  items: PlanItem[];
  planId?: string | null;
  weekTitle?: string | null;
  weekCalories?: number | null;
  weekProteinG?: number | null;
  weekCarbsG?: number | null;
  weekFatG?: number | null;
  onGenerate?: () => void;
  onHistory?: () => void;
  generation?: PlanGenerationProgress | null;
  numDays?: number;
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
  onGenerate,
  onHistory,
  generation,
  numDays = 7,
  className,
}: TodayMealsPanelProps) {
  const hasWeekNutrition =
    weekCalories != null &&
    weekProteinG != null &&
    weekCarbsG != null;
  const creating = isGenerationInFlight(generation);

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
          {creating
            ? "This week is being created."
            : "No active plan nutrition yet."}
        </p>
      )}
      <GenerationProgressBar generation={generation} numDays={numDays} />
      {hasWeekNutrition ? <DisclaimerBanner /> : null}

      <div className="flex items-stretch gap-2">
        {onGenerate ? (
          <button
            type="button"
            onClick={onGenerate}
            className="btn-primary min-w-0 flex-1"
          >
            Generate New Plan
          </button>
        ) : (
          <Link
            href={planId ? `/plans/${planId}` : "/plans"}
            className="btn-primary min-w-0 flex-1"
          >
            Generate New Plan
          </Link>
        )}
        {onHistory ? (
          <button
            type="button"
            onClick={onHistory}
            aria-label="Past conversations"
            title="Past conversations"
            className="flex size-12 shrink-0 items-center justify-center rounded-pill border-[1.5px] border-primary bg-transparent text-primary"
          >
            <History className="size-5" aria-hidden />
          </button>
        ) : null}
      </div>
      {planId ? (
        <Link
          href={`/plans/${planId}`}
          className="font-mono text-[10px] uppercase tracking-[0.08em] text-primary no-underline"
        >
          Open this week
        </Link>
      ) : null}

      <EyebrowLabel className="mt-2">Today&apos;s Meals</EyebrowLabel>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto">
        {items.length === 0 ? (
          <p className="font-sans text-body-sm italic text-text-muted">
            {creating
              ? "Building this week in the background…"
              : "No meals scheduled for today yet."}
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
