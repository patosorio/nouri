"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DayTab } from "@/components/plans/DayTab";
import { GenerateDrawer } from "@/components/plans/GenerateDrawer";
import { GenerationProgressBar } from "@/components/plans/GenerationProgressBar";
import { JuiceSlotRow } from "@/components/plans/JuiceSlotRow";
import { MealSlotCard } from "@/components/plans/MealSlotCard";
import { RecipeDetailPanel } from "@/components/plans/RecipeDetailPanel";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageShell } from "@/components/shared/PageShell";
import { DisclaimerBanner } from "@/components/shared/DisclaimerBanner";
import { NutritionStrip } from "@/components/shared/NutritionStrip";
import { SourcingPolicyBadge } from "@/components/shared/SourcingPolicyBadge";
import { useRightPanel } from "@/components/shared/right-panel-context";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlan } from "@/hooks";
import { ApiError, apiClient } from "@/lib/api-client";
import type { JuiceColor, JuiceSize, JuiceTime, PlanItem } from "@/lib/types";

interface PlanDetailViewProps {
  planId: string;
}

const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

function weekdayLabel(weekStartDate: string, dayNumber: number): string {
  const start = new Date(`${weekStartDate}T12:00:00`);
  if (Number.isNaN(start.getTime())) {
    return WEEKDAY_SHORT[(dayNumber - 1) % 7] ?? `Day ${dayNumber}`;
  }
  const d = new Date(start);
  d.setDate(start.getDate() + (dayNumber - 1));
  return WEEKDAY_SHORT[(d.getDay() + 6) % 7] ?? `Day ${dayNumber}`;
}

function asJuiceMeta(item: PlanItem): {
  time: JuiceTime;
  size: JuiceSize;
  color: JuiceColor;
} {
  return {
    time: (item.juice_time as JuiceTime | null) ?? "afternoon",
    size: "oz16_ml500",
    color: "green",
  };
}

export function PlanDetailView({ planId }: PlanDetailViewProps) {
  const queryClient = useQueryClient();
  const { setRightPanel } = useRightPanel();
  const { data: plan, isLoading, isError } = usePlan(planId);
  const [activeDay, setActiveDay] = useState(1);
  const [focusedItemId, setFocusedItemId] = useState<string | null>(null);
  const [panelMode, setPanelMode] = useState<"view" | "swap">("view");
  const [generateOpen, setGenerateOpen] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const day = useMemo(
    () => plan?.days.find((d) => d.day_number === activeDay) ?? plan?.days[0],
    [plan, activeDay],
  );

  const focusedItem =
    day?.items.find((item) => item.id === focusedItemId) ?? null;

  const weekAvg = useMemo(() => {
    if (!plan?.days.length) return null;
    const summary = plan.nutrition_summary;
    if (summary?.avg_daily_calories != null) {
      return {
        calories: summary.avg_daily_calories,
        protein: summary.avg_daily_protein_g ?? 0,
        carbs: summary.avg_daily_carbs_g ?? 0,
      };
    }
    const n = plan.days.length;
    const totals = plan.days.reduce(
      (acc, d) => ({
        calories: acc.calories + (d.calories_actual ?? d.calories_target ?? 0),
        protein: acc.protein + (d.protein_g_actual ?? d.protein_g_target ?? 0),
        carbs: acc.carbs + (d.carbs_g_actual ?? d.carbs_g_target ?? 0),
      }),
      { calories: 0, protein: 0, carbs: 0 },
    );
    return {
      calories: Math.round(totals.calories / n),
      protein: Math.round(totals.protein / n),
      carbs: Math.round(totals.carbs / n),
    };
  }, [plan]);

  const approveMutation = useMutation({
    mutationFn: () => apiClient.updatePlanStatus(planId, "approved"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["plans", planId] });
      void queryClient.invalidateQueries({ queryKey: ["plans"] });
      void queryClient.invalidateQueries({ queryKey: ["calendar"] });
    },
  });

  const swapMutation = useMutation({
    mutationFn: (itemId: string) =>
      apiClient.swapPlanItem(planId, itemId, { reason: "User requested swap" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["plans", planId] });
    },
  });

  useEffect(() => {
    if (!focusedItem) {
      setRightPanel(null);
      return;
    }

    const item = focusedItem;
    const dayLabel = plan
      ? weekdayLabel(plan.week_start_date, item.day_number)
      : "";
    setRightPanel(
      <RecipeDetailPanel
        planItem={item}
        mode={panelMode}
        dayLabel={`${item.slot.replaceAll("_", " ")} · ${dayLabel}`}
        onClose={() => setFocusedItemId(null)}
        onSwap={() => {
          setPanelMode("swap");
          void swapMutation.mutateAsync(item.id);
        }}
        onApprove={
          plan?.status !== "approved"
            ? () => {
                void approveMutation.mutateAsync();
              }
            : undefined
        }
      />,
      { width: 360 },
    );

    return () => setRightPanel(null);
  }, [
    focusedItem,
    panelMode,
    plan,
    setRightPanel,
    swapMutation.mutateAsync,
    approveMutation.mutateAsync,
  ]);

  async function exportPdf() {
    setExporting(true);
    setExportError(null);
    try {
      const blob = await apiClient.exportPlanPdf(planId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `nouri-plan-${planId.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setExportError("PDF export requires a Pro plan.");
      } else if (err instanceof ApiError && err.status === 404) {
        setExportError("PDF export isn’t available yet for this plan.");
      } else {
        setExportError("Could not export PDF. Try again later.");
      }
    } finally {
      setExporting(false);
    }
  }

  if (isLoading) {
    return (
      <PageShell>
        <Skeleton className="mb-4 h-10 w-64" />
        <Skeleton className="mb-4 h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </PageShell>
    );
  }

  if (isError || !plan) {
    return (
      <PageShell>
        <p className="font-sans text-body text-cta">
          Plan not found or unavailable.
        </p>
        <p className="mt-2 font-sans text-sm text-text-muted">
          Confirm the API is running and you are signed in as the plan owner.
        </p>
      </PageShell>
    );
  }

  const statusLabel =
    plan.status.charAt(0).toUpperCase() +
    plan.status.slice(1).replaceAll("_", " ");

  // Draft stubs from Generate have no PlanDay rows until the worker writes them.
  if (!day) {
    return (
      <PageShell className="pb-16">
        <PageHeader
          eyebrow="Meal Plan"
          title={`Week of ${new Date(`${plan.week_start_date}T12:00:00`).toLocaleDateString(
            "en-US",
            { month: "long", day: "numeric" },
          )}`}
          description={`${plan.num_days} days · ${statusLabel}`}
          actions={
            <button
              type="button"
              onClick={() => setGenerateOpen(true)}
              className="btn-primary"
            >
              Generate New Plan
            </button>
          }
        />
        <div className="max-w-[560px] rounded-card border border-border bg-white px-6 py-8">
          <p className="font-sans text-body text-text">
            {plan.generation?.status === "failed"
              ? "Generation failed."
              : "This plan is being created in the background."}
          </p>
          <p className="mt-2 font-sans text-sm text-text-muted">
            {plan.generation?.status === "failed"
              ? plan.generation.error_message ??
                "You can generate a new plan anytime."
              : "You can keep using the app. We'll notify you when it's ready."}
          </p>
          <GenerationProgressBar
            generation={plan.generation}
            numDays={plan.num_days}
          />
        </div>
        <GenerateDrawer open={generateOpen} onOpenChange={setGenerateOpen} />
      </PageShell>
    );
  }

  const mealItems = day.items.filter((item) => item.slot !== "juice");
  const juiceItems = day.items.filter((item) => item.slot === "juice");
  const needsApproval = plan.status === "reviewing" || plan.status === "draft";

  return (
    <PageShell className="pb-16">
      <PageHeader
        eyebrow="Meal Plan"
        title={`Week of ${new Date(`${plan.week_start_date}T12:00:00`).toLocaleDateString(
          "en-US",
          { month: "long", day: "numeric" },
        )}`}
        description={`${plan.num_days} days · ${statusLabel}${
          weekAvg ? ` · ${weekAvg.calories.toLocaleString()} kcal/day avg` : ""
        }`}
        actions={
          <>
            {needsApproval ? (
              <button
                type="button"
                onClick={() => void approveMutation.mutateAsync()}
                disabled={approveMutation.isPending}
                className="btn-primary"
              >
                {approveMutation.isPending ? "Approving…" : "Approve plan"}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setGenerateOpen(true)}
              className={needsApproval ? "btn-ghost" : "btn-primary"}
            >
              Generate New Plan
            </button>
            <button
              type="button"
              onClick={() => void exportPdf()}
              disabled={exporting}
              className="btn-ghost disabled:opacity-50"
            >
              {exporting ? "Exporting…" : "Export PDF"}
            </button>
          </>
        }
      />

      {exportError ? (
        <p className="mb-4 font-sans text-body-sm text-cta">{exportError}</p>
      ) : null}
      {approveMutation.isError ? (
        <p className="mb-4 font-sans text-body-sm text-cta">
          {approveMutation.error instanceof ApiError
            ? approveMutation.error.message
            : "Could not approve this plan."}
        </p>
      ) : null}

      <NutritionStrip
        title="Weekly Nutrition"
        avgLabels
        calories={weekAvg?.calories ?? 0}
        proteinG={weekAvg?.protein ?? 0}
        carbsG={weekAvg?.carbs ?? 0}
        className="mb-7"
        trailing={
          plan.recipe_usage_policy ? (
            <SourcingPolicyBadge policy={plan.recipe_usage_policy} />
          ) : null
        }
      />

      <DisclaimerBanner className="mb-7" />

      <div className="mb-6 flex w-fit flex-wrap gap-1.5 rounded-pill bg-surface p-1.5">
        {plan.days.map((d) => (
          <DayTab
            key={d.day_number}
            label={weekdayLabel(plan.week_start_date, d.day_number)}
            active={d.day_number === day.day_number}
            onSelect={() => {
              setActiveDay(d.day_number);
              setFocusedItemId(null);
            }}
          />
        ))}
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-4">
        <span className="shrink-0 whitespace-nowrap rounded-pill bg-primary-dark px-4 py-2 font-mono text-eyebrow text-highlight">
          {Math.round(day.calories_actual ?? day.calories_target ?? 0).toLocaleString()}{" "}
          kcal
        </span>
        <span className="shrink-0 whitespace-nowrap rounded-pill bg-primary-dark px-4 py-2 font-mono text-eyebrow text-highlight">
          {Math.round(day.protein_g_actual ?? day.protein_g_target ?? 0)}g protein
        </span>
        <span className="shrink-0 whitespace-nowrap rounded-pill bg-primary-dark px-4 py-2 font-mono text-eyebrow text-highlight">
          {Math.round(day.carbs_g_actual ?? day.carbs_g_target ?? 0)}g carbs
        </span>
        <span className="shrink-0 whitespace-nowrap rounded-pill bg-primary-dark px-4 py-2 font-mono text-eyebrow text-highlight">
          {Math.round(day.fat_g_actual ?? day.fat_g_target ?? 0)}g fat
        </span>
      </div>

      <div className="flex max-w-[760px] flex-col gap-4">
        {mealItems.map((item) => {
          // Screen-09 uses approved card chrome + SourceBadge for reviewing plans;
          // only the focused card gets the elevated focused ring.
          let reviewState: "approved" | "pending-review" | "focused" =
            "approved";
          if (item.id === focusedItemId) reviewState = "focused";

          return (
            <MealSlotCard
              key={item.id}
              planItem={item}
              reviewState={reviewState}
              onSelect={() => {
                setPanelMode("view");
                setFocusedItemId(item.id);
              }}
              onSwap={() => {
                setPanelMode("swap");
                setFocusedItemId(item.id);
                void swapMutation.mutateAsync(item.id);
              }}
            />
          );
        })}

        {juiceItems.map((item) => {
          const meta = asJuiceMeta(item);
          return (
            <JuiceSlotRow
              key={item.id}
              name={item.name}
              ingredients={item.description ?? undefined}
              timeOfDay={meta.time}
              size={meta.size}
              color={meta.color}
            />
          );
        })}
      </div>

      <GenerateDrawer open={generateOpen} onOpenChange={setGenerateOpen} />
    </PageShell>
  );
}

export function PlansListActions() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn-primary"
      >
        Generate New Plan
      </button>
      <GenerateDrawer open={open} onOpenChange={setOpen} />
    </>
  );
}
