import { RawCookedTag } from "@/components/shared/RawCookedTag";
import { toRawCookedTag } from "@/lib/cooking";
import type { CookingType } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RecipeCardInlineProps {
  title: string;
  description?: string | null;
  prepMinutes?: number | null;
  servings?: number | null;
  caloriesKcal?: number | null;
  proteinG?: number | null;
  cookingType: CookingType;
  className?: string;
  onSave?: () => void;
  onView?: () => void;
}

export function RecipeCardInline({
  title,
  description,
  prepMinutes,
  servings,
  caloriesKcal,
  proteinG,
  cookingType,
  className,
  onSave,
  onView,
}: RecipeCardInlineProps) {
  const stats = [
    prepMinutes != null ? `Prep ${prepMinutes} min` : null,
    servings != null ? `Serves ${servings}` : null,
    caloriesKcal != null ? `${Math.round(caloriesKcal)} kcal` : null,
    proteinG != null ? `${Math.round(proteinG)}g protein` : null,
  ]
    .filter(Boolean)
    .join(" · ")
    .toUpperCase();

  return (
    <article
      className={cn(
        "mt-3 max-w-[380px] overflow-hidden rounded-card border border-border bg-surface",
        className,
      )}
    >
      <div className="h-[150px] bg-gradient-to-br from-primary/25 to-highlight/25" />
      <div className="flex flex-col gap-2 px-[18px] py-4">
        <RawCookedTag type={toRawCookedTag(cookingType)} />
        <h3 className="m-0 font-sans text-title font-medium text-text">
          {title}
        </h3>
        {description ? (
          <p className="m-0 font-sans text-body-sm italic text-text-muted">
            {description}
          </p>
        ) : null}
        {stats ? (
          <p className="m-0 font-mono text-eyebrow-sm tracking-[0.04em] text-text-muted">
            {stats}
          </p>
        ) : null}
        {(onSave || onView) && (
          <div className="mt-1 flex gap-2.5">
            {onSave ? (
              <button
                type="button"
                onClick={onSave}
                className="btn-primary"
              >
                Save Recipe
              </button>
            ) : null}
            {onView ? (
              <button
                type="button"
                onClick={onView}
                className="btn-ghost"
              >
                See Full Recipe
              </button>
            ) : null}
          </div>
        )}
      </div>
    </article>
  );
}
