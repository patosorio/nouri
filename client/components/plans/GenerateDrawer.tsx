"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";
import { useProfile } from "@/hooks";
import { apiClient } from "@/lib/api-client";
import type {
  CookingType,
  DietType,
  RecipeUsagePolicy,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface GenerateDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DAY_OPTIONS = [1, 3, 5, 7, 14] as const;

const DIET_LABELS: Record<DietType, string> = {
  plant_based: "Plant-Based",
  vegan: "Vegan",
  wfpb: "Whole Food Plant-Based",
  pescatarian: "Pescatarian",
  flexitarian: "Flexitarian",
  omnivore: "Omnivore",
  no_pork: "No Pork",
};

const COOKING_OPTIONS: {
  value: CookingType;
  label: string;
  barClassName: string;
  barStyle?: CSSProperties;
}[] = [
  {
    value: "raw_100",
    label: "100% Raw",
    barClassName: "bg-primary",
  },
  {
    value: "raw_80_cooked_20",
    label: "80/20 Raw-Cooked",
    barClassName: "",
    barStyle: {
      background:
        "linear-gradient(180deg, var(--color-primary) 80%, var(--color-cta) 80%)",
    },
  },
  {
    value: "raw_70_cooked_30",
    label: "70/30 Raw-Cooked",
    barClassName: "",
    barStyle: {
      background:
        "linear-gradient(180deg, var(--color-primary) 70%, var(--color-cta) 70%)",
    },
  },
  {
    value: "raw_50_cooked_50",
    label: "50/50",
    barClassName: "",
    barStyle: {
      background:
        "linear-gradient(180deg, var(--color-primary) 50%, var(--color-cta) 50%)",
    },
  },
  {
    value: "cooked_100",
    label: "100% Cooked",
    barClassName: "bg-cta",
  },
];

const SOURCING_OPTIONS: {
  value: RecipeUsagePolicy;
  title: string;
  description: string;
}[] = [
  {
    value: "prefer_saved",
    title: "Saved First",
    description: "Prefer your saved recipes; generate only when nothing matches.",
  },
  {
    value: "balanced",
    title: "Balanced",
    description: "Mix of saved and newly generated recipes.",
  },
  {
    value: "prefer_new",
    title: "Prefer New",
    description: "Generate fresh recipes; use saved only when specified.",
  },
];

function FieldLabel({ children }: { children: string }) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
      {children}
    </span>
  );
}

function nextMondayIso(): string {
  const d = new Date();
  const day = d.getDay();
  const diff = day === 0 ? 1 : 8 - day;
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
}

async function pollJob(jobId: string): Promise<string | null> {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const job = await apiClient.getJob(jobId);
    if (job.status === "completed") {
      const planId =
        job.plan_id ??
        (typeof job.result?.plan_id === "string" ? job.result.plan_id : null);
      return planId;
    }
    if (job.status === "failed" || job.status === "cancelled") {
      throw new Error(job.error_message ?? "Plan generation failed");
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("Plan generation timed out");
}

export function GenerateDrawer({ open, onOpenChange }: GenerateDrawerProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: profile } = useProfile();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [numDays, setNumDays] = useState<number>(7);
  const [weekStartDate, setWeekStartDate] = useState("");
  const [dietType, setDietType] = useState<DietType>("plant_based");
  const [cookingType, setCookingType] =
    useState<CookingType>("raw_80_cooked_20");
  const [calorieTarget, setCalorieTarget] = useState(2050);
  const [sourcing, setSourcing] =
    useState<RecipeUsagePolicy>("prefer_saved");
  const [includeJuicing, setIncludeJuicing] = useState(false);
  const [activeMeals, setActiveMeals] = useState({
    breakfast: false,
    lunch: true,
    dinner: true,
  });
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!open || !profile) return;
    setNumDays(7);
    setWeekStartDate(nextMondayIso());
    setDietType(profile.diet_type);
    setCookingType(profile.cooking_type);
    setCalorieTarget(profile.calorie_target ?? 2050);
    setSourcing(profile.recipe_usage_policy);
    setIncludeJuicing(profile.juicing_enabled);
    setNotes("");
    setSubmitError(null);
  }, [open, profile]);

  async function handleSubmit() {
    if (!profile || !weekStartDate) {
      setSubmitError("Pick a week start date.");
      return;
    }
    setSubmitError(null);
    setSubmitting(true);

    try {
      const job = await apiClient.generatePlan({
        num_days: numDays,
        diet_type: dietType,
        cooking_type: cookingType,
        calorie_target: calorieTarget,
        recipe_usage_policy: sourcing,
        include_juicing: includeJuicing,
        notes: notes.trim() || null,
      });

      const planId = await pollJob(job.id);
      await queryClient.invalidateQueries({ queryKey: ["plans"] });
      onOpenChange(false);

      if (planId) {
        router.push(`/plans/${planId}`);
      } else {
        router.push("/plans");
      }
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Could not generate plan. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-full gap-0 border-l border-border bg-bg p-0 shadow-[-16px_0_48px_rgba(30,53,87,0.25)] sm:max-w-[520px]"
      >
        <div className="flex items-center justify-between border-b border-border bg-surface px-7 py-6">
          <SheetTitle className="font-sans text-title font-semibold text-text">
            Generate <em>New Plan</em>
          </SheetTitle>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Close"
            className="border-0 bg-transparent text-[22px] leading-none text-text-muted"
          >
            ×
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-[26px] overflow-y-auto px-7 py-[26px]">
          <div className="flex flex-col gap-2.5">
            <FieldLabel>How many days?</FieldLabel>
            <div className="flex gap-1 rounded-pill border border-border bg-surface p-1">
              {DAY_OPTIONS.map((days) => (
                <button
                  key={days}
                  type="button"
                  onClick={() => setNumDays(days)}
                  className={cn(
                    "flex-1 rounded-pill py-2.5 text-center font-mono text-xs",
                    numDays === days
                      ? "bg-primary text-white"
                      : "bg-transparent text-text-muted",
                  )}
                >
                  {days}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2.5">
            <FieldLabel>Week Start Date</FieldLabel>
            <input
              type="date"
              value={weekStartDate}
              onChange={(e) => setWeekStartDate(e.target.value)}
              className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none focus:border-primary"
            />
          </div>

          <div className="flex flex-col gap-2.5">
            <FieldLabel>Diet Type</FieldLabel>
            <div className="flex items-center justify-between gap-3 rounded-xl border-[1.5px] border-primary bg-primary/[0.06] px-4 py-3">
              <span className="whitespace-nowrap font-sans font-medium text-text">
                {DIET_LABELS[dietType]}
              </span>
              <Link
                href="/profile"
                className="shrink-0 font-mono text-[11px] uppercase tracking-wide text-primary no-underline"
              >
                Change
              </Link>
            </div>
          </div>

          <div className="flex flex-col gap-2.5">
            <FieldLabel>Cooking Type</FieldLabel>
            <div className="flex flex-col gap-2">
              {COOKING_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setCookingType(option.value)}
                  className={cn(
                    "flex items-center gap-3 rounded-[10px] border-[1.5px] bg-surface px-3.5 py-2.5 text-left",
                    cookingType === option.value
                      ? "border-primary bg-primary/[0.06]"
                      : "border-border",
                  )}
                >
                  <span
                    className={cn(
                      "h-6 w-1.5 shrink-0 rounded",
                      option.barClassName,
                    )}
                    style={option.barStyle}
                    aria-hidden
                  />
                  <span className="font-sans text-body text-text">
                    {option.label}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2.5">
            <FieldLabel>Daily Calorie Target</FieldLabel>
            <input
              type="number"
              min={800}
              max={5000}
              step={50}
              value={calorieTarget}
              onChange={(e) => setCalorieTarget(Number(e.target.value))}
              className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none focus:border-primary"
            />
          </div>

          <div className="flex flex-col gap-2.5">
            <FieldLabel>Recipe Sourcing Policy</FieldLabel>
            <div className="flex flex-col gap-2.5">
              {SOURCING_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setSourcing(option.value)}
                  className={cn(
                    "rounded-xl border-[1.5px] bg-surface px-4 py-3.5 text-left",
                    sourcing === option.value
                      ? "border-primary border-l-4 bg-primary/[0.05]"
                      : "border-border",
                  )}
                >
                  <p className="m-0 font-sans font-medium text-text">
                    {option.title}
                  </p>
                  <p className="m-0 mt-0.5 font-sans text-[0.85rem] text-text-muted">
                    {option.description}
                  </p>
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <FieldLabel>Include Juicing</FieldLabel>
              <button
                type="button"
                role="switch"
                aria-checked={includeJuicing}
                onClick={() => setIncludeJuicing((v) => !v)}
                className={cn(
                  "relative h-[22px] w-10 rounded-pill transition-colors",
                  includeJuicing ? "bg-primary" : "bg-border",
                )}
              >
                <span
                  className={cn(
                    "absolute top-0.5 h-[18px] w-[18px] rounded-full bg-white transition-all",
                    includeJuicing ? "right-0.5" : "left-0.5",
                  )}
                />
              </button>
            </div>

            {includeJuicing ? (
              <div className="flex flex-col gap-[18px] rounded-xl border border-border bg-surface p-4">
                <div>
                  <FieldLabel>Active Solid Meals</FieldLabel>
                  <div className="mt-2 flex gap-2.5">
                    {(
                      [
                        ["breakfast", "Breakfast"],
                        ["lunch", "Lunch"],
                        ["dinner", "Dinner"],
                      ] as const
                    ).map(([key, label]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() =>
                          setActiveMeals((prev) => ({
                            ...prev,
                            [key]: !prev[key],
                          }))
                        }
                        className={cn(
                          "flex-1 rounded-pill border px-3.5 py-2 text-center font-mono text-[11px] tracking-[0.04em]",
                          activeMeals[key]
                            ? "border-primary bg-primary text-white"
                            : "border-border bg-surface text-text-muted",
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="m-0 font-sans text-[0.85rem] italic text-text-muted">
                  Juice slot timing and colors are applied when the plan is
                  generated.
                </p>
              </div>
            ) : null}
          </div>

          <div className="flex flex-col gap-2.5">
            <FieldLabel>Notes for This Week</FieldLabel>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Anything specific for this week?"
              rows={3}
              className="min-h-20 w-full resize-y rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none placeholder:text-text-muted focus:border-primary"
            />
          </div>

          {submitError ? (
            <p className="font-sans text-body-sm text-cta">{submitError}</p>
          ) : null}
        </div>

        <div className="border-t border-border bg-surface px-7 py-5">
          <button
            type="button"
            disabled={submitting || !profile}
            onClick={() => void handleSubmit()}
            className="btn-primary w-full"
          >
            {submitting ? "Generating…" : "Generate Plan →"}
          </button>
          <p className="mt-2.5 text-center font-mono text-[10px] text-text-muted">
            Usually ready in 30–60 seconds
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
