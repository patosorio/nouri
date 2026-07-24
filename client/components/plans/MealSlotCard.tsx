"use client";

import { NeedsReviewBadge } from "@/components/shared/NeedsReviewBadge";
import { RawCookedTag } from "@/components/shared/RawCookedTag";
import { SourceBadge } from "@/components/shared/SourceBadge";
import { toRawCookedTag } from "@/lib/cooking";
import type { PlanItem, PlanSlot } from "@/lib/types";
import { cn } from "@/lib/utils";

interface MealSlotCardProps {
  planItem: PlanItem;
  reviewState: "approved" | "pending-review" | "focused";
  slotTime?: string | null;
  onSelect?: () => void;
  onSwap?: () => void;
  className?: string;
}

const SLOT_LABEL: Partial<Record<PlanSlot, string>> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack",
  juice: "Juice",
  extra_morning: "Extra Morning",
  extra_afternoon: "Extra Afternoon",
  extra_evening: "Extra Evening",
};

const DEFAULT_SLOT_TIME: Partial<Record<PlanSlot, string>> = {
  breakfast: "07:30",
  lunch: "12:30",
  dinner: "19:00",
};

export function MealSlotCard({
  planItem,
  reviewState,
  slotTime,
  onSelect,
  onSwap,
  className,
}: MealSlotCardProps) {
  const time = slotTime ?? DEFAULT_SLOT_TIME[planItem.slot] ?? null;
  const slotLabel = SLOT_LABEL[planItem.slot] ?? planItem.slot.replaceAll("_", " ");
  const eyebrow = time ? `${slotLabel} · ${time}` : slotLabel;

  const stats = [
    planItem.prep_minutes != null ? `Prep ${planItem.prep_minutes} min` : null,
    planItem.calories != null ? `${Math.round(planItem.calories)} kcal` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.();
        }
      }}
      className={cn(
        "flex cursor-pointer flex-col gap-2.5 rounded-card border border-border bg-surface px-[22px] py-[18px]",
        reviewState === "pending-review" &&
          "border-cta shadow-[0_0_0_1px_rgba(244,91,99,0.25)]",
        reviewState === "approved" && "border-primary",
        reviewState === "focused" &&
          "border-primary shadow-[0_8px_24px_rgba(30,53,87,0.14)]",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-eyebrow-sm uppercase tracking-[0.14em] text-text-muted">
          {eyebrow}
        </span>
        <RawCookedTag type={toRawCookedTag(planItem.prep_method)} />
      </div>

      <h3 className="m-0 font-sans text-title font-medium text-text">
        {planItem.name}
      </h3>
      {planItem.description ? (
        <p className="m-0 font-sans text-body-sm italic text-text-muted">
          {planItem.description}
        </p>
      ) : null}
      {stats ? (
        <p className="m-0 font-mono text-eyebrow-sm tracking-[0.05em] text-text-muted">
          {stats}
        </p>
      ) : null}

      <div className="mt-1 flex items-center justify-between gap-3">
        {reviewState === "pending-review" ? (
          <NeedsReviewBadge />
        ) : (
          <SourceBadge source={planItem.item_source} />
        )}
        <div className="flex gap-2">
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-surface text-sm text-primary"
            onClick={(e) => {
              e.stopPropagation();
              onSwap?.();
            }}
            aria-label="Swap meal"
          >
            ↔
          </button>
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-surface text-sm text-primary"
            onClick={(e) => {
              e.stopPropagation();
              onSelect?.();
            }}
            aria-label="Open meal"
          >
            →
          </button>
        </div>
      </div>
    </article>
  );
}
