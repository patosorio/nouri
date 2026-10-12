"use client";

import Link from "next/link";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { RawCookedTag } from "@/components/shared/RawCookedTag";
import { SourceBadge } from "@/components/shared/SourceBadge";
import { useRecipe } from "@/hooks";
import { toRawCookedTag } from "@/lib/cooking";
import type { PlanItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RecipeDetailPanelProps {
  planItem: PlanItem | null;
  mode: "view" | "swap";
  dayLabel?: string;
  onClose: () => void;
  onSwap?: () => void;
  onApprove?: () => void;
  className?: string;
}

export function RecipeDetailPanel({
  planItem,
  mode,
  dayLabel,
  onClose,
  onSwap,
  onApprove,
  className,
}: RecipeDetailPanelProps) {
  const { data: recipe, isLoading } = useRecipe(
    planItem?.recipe_id ?? undefined,
  );

  if (!planItem) return null;

  return (
    <div className={cn("flex h-full flex-col", className)}>
      <div className="mb-2 flex items-center justify-between">
        <EyebrowLabel className="m-0">
          {dayLabel ?? (mode === "swap" ? "Swap meal" : "Recipe")}
        </EyebrowLabel>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="border-0 bg-transparent text-[18px] text-text-muted"
        >
          ×
        </button>
      </div>

      <div className="mb-4 h-40 w-full rounded-card bg-gradient-to-br from-primary/25 to-highlight/30" />

      <h2 className="mb-2 mt-1 font-sans text-heading font-medium text-text">
        {planItem.name}
      </h2>
      {planItem.description ? (
        <p className="mb-3.5 mt-0 font-sans text-body-sm italic text-text-muted">
          {planItem.description}
        </p>
      ) : null}

      <div className="mb-4 flex flex-wrap gap-2">
        <RawCookedTag type={toRawCookedTag(planItem.prep_method)} />
        <SourceBadge source={planItem.item_source} />
      </div>

      {planItem.calories != null ? (
        <>
          <p className="mb-2 mt-[18px] font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-text-muted">
            Nutrition · Per Serving
          </p>
          <div className="mb-4 flex gap-4 rounded-xl bg-primary-dark px-4 py-3.5 text-white">
            <div className="flex flex-col">
              <strong className="font-mono text-base font-medium text-highlight">
                {Math.round(planItem.calories)}
              </strong>
              <span className="font-mono text-label uppercase text-white/60">
                Kcal
              </span>
            </div>
            <div className="flex flex-col">
              <strong className="font-mono text-base font-medium text-highlight">
                {Math.round(planItem.protein_g ?? 0)}g
              </strong>
              <span className="font-mono text-label uppercase text-white/60">
                Protein
              </span>
            </div>
            <div className="flex flex-col">
              <strong className="font-mono text-base font-medium text-highlight">
                {Math.round(planItem.carbs_g ?? 0)}g
              </strong>
              <span className="font-mono text-label uppercase text-white/60">
                Carbs
              </span>
            </div>
            <div className="flex flex-col">
              <strong className="font-mono text-base font-medium text-highlight">
                {Math.round(planItem.fat_g ?? 0)}g
              </strong>
              <span className="font-mono text-label uppercase text-white/60">
                Fat
              </span>
            </div>
          </div>
        </>
      ) : null}

      <p className="mb-2 mt-[18px] font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-text-muted">
        Key Ingredients
      </p>
      {isLoading ? (
        <p className="font-sans text-body-sm italic text-text-muted">Loading…</p>
      ) : recipe ? (
        <div>
          {recipe.ingredients.slice(0, 6).map((ing, idx) => (
            <div
              key={ing.id ?? `${ing.ingredient_id}-${idx}`}
              className="flex justify-between border-b border-primary/10 py-1.5 text-[0.9rem]"
            >
              <span>{ing.ingredient_name ?? "ingredient"}</span>
              <span>
                {ing.amount} {ing.unit}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="font-sans text-body-sm italic text-text-muted">
          Full recipe details aren&apos;t saved yet for this slot.
        </p>
      )}

      <div className="mt-5 flex flex-col gap-2.5">
        <button
          type="button"
          onClick={onSwap}
          className="w-full btn-primary"
        >
          Swap This Meal
        </button>
        {onApprove ? (
          <button
            type="button"
            onClick={onApprove}
            className="w-full btn-ghost"
          >
            Approve plan
          </button>
        ) : null}
        {planItem.recipe_id ? (
          <Link
            href={`/recipes/${planItem.recipe_id}`}
            className="inline-flex w-full items-center justify-center rounded-pill border-[1.5px] border-primary px-[22px] py-[11px] font-sans text-btn font-medium text-primary hover:bg-primary/[0.08]"
          >
            View Full Recipe
          </Link>
        ) : null}
      </div>
    </div>
  );
}
