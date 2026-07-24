"use client";

import { FilterChip } from "@/components/recipes/FilterChip";
import type {
  CookingType,
  DietType,
  PrepMethod,
  RecipeFilters,
  RecipeSource,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface FilterPanelProps {
  filters: RecipeFilters;
  onFiltersChange: (filters: RecipeFilters) => void;
  className?: string;
}

const DIET_TYPES: { value: DietType; label: string }[] = [
  { value: "plant_based", label: "Plant-Based" },
  { value: "vegan", label: "Vegan" },
  { value: "wfpb", label: "Whole Food Plant-Based" },
  { value: "pescatarian", label: "Pescatarian" },
  { value: "flexitarian", label: "Flexitarian" },
  { value: "omnivore", label: "Omnivore" },
  { value: "no_pork", label: "No Pork" },
];

const COOKING_TYPES: { value: CookingType; label: string }[] = [
  { value: "raw_100", label: "100% Raw" },
  { value: "raw_80_cooked_20", label: "80/20 Raw-Cooked" },
  { value: "raw_70_cooked_30", label: "70/30 Raw-Cooked" },
  { value: "raw_50_cooked_50", label: "50/50" },
  { value: "cooked_100", label: "100% Cooked" },
];

const DIET_SUBTYPES = [
  "Keto",
  "High Protein",
  "Low Carb",
  "High Fiber",
  "Detox",
  "Anti-Inflammatory",
] as const;

const CUISINES = [
  { value: "mediterranean", label: "Mediterranean" },
  { value: "italian", label: "Italian" },
  { value: "asian", label: "Asian" },
  { value: "indian", label: "Indian" },
  { value: "middle_eastern", label: "Middle Eastern" },
  { value: "mexican", label: "Mexican" },
  { value: "japanese", label: "Japanese" },
  { value: "thai", label: "Thai" },
] as const;

const PREP_METHODS: { value: PrepMethod; label: string }[] = [
  { value: "raw", label: "Raw" },
  { value: "juiced", label: "Juiced" },
  { value: "blended", label: "Blended" },
  { value: "dehydrated", label: "Dehydrated" },
  { value: "steamed", label: "Steamed" },
  { value: "baked", label: "Baked" },
];

const SOURCES: { value: RecipeSource; label: string }[] = [
  { value: "ai_generated", label: "AI Generated" },
  { value: "manual", label: "Saved" },
  { value: "imported_text", label: "Imported" },
  { value: "imported_image", label: "From Image" },
];

const JUICE_COLORS = [
  "#8E6FD1",
  "#6FCF7B",
  "#F3E751",
  "#F2A34D",
  "#F45B63",
  "#F08FAE",
  "#4980DA",
];

function GroupLabel({ children }: { children: string }) {
  return (
    <p className="mb-2.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
      {children}
    </p>
  );
}

export function FilterPanel({
  filters,
  onFiltersChange,
  className,
}: FilterPanelProps) {
  function patch(partial: Partial<RecipeFilters>) {
    onFiltersChange({ ...filters, ...partial, offset: 0 });
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-[22px] rounded-card border border-border bg-surface px-[26px] py-6",
        className,
      )}
    >
      <div>
        <GroupLabel>Diet Type</GroupLabel>
        <div className="flex flex-wrap gap-2">
          {DIET_TYPES.map(({ value, label }) => (
            <FilterChip
              key={value}
              value={value}
              label={label}
              selected={filters.diet_type === value}
              onToggle={() =>
                patch({
                  diet_type: filters.diet_type === value ? undefined : value,
                })
              }
            />
          ))}
        </div>
      </div>

      <div>
        <GroupLabel>Cooking Type</GroupLabel>
        <div className="flex flex-wrap gap-2">
          {COOKING_TYPES.map(({ value, label }) => (
            <FilterChip
              key={value}
              value={value}
              label={label}
              selected={filters.cooking_type === value}
              onToggle={() =>
                patch({
                  cooking_type:
                    filters.cooking_type === value ? undefined : value,
                })
              }
            />
          ))}
        </div>
      </div>

      <div>
        <GroupLabel>Diet Subtypes</GroupLabel>
        <div className="flex flex-wrap gap-2">
          {DIET_SUBTYPES.map((label) => (
            <FilterChip
              key={label}
              value={label}
              label={label}
              selected={false}
              onToggle={() => {
                // Subtype multi-select awaits API filter support.
              }}
            />
          ))}
        </div>
      </div>

      <div>
        <GroupLabel>Cuisine</GroupLabel>
        <div className="flex flex-wrap gap-2">
          {CUISINES.map(({ value, label }) => {
            const selected = filters.cuisine?.includes(value) ?? false;
            return (
              <FilterChip
                key={value}
                value={value}
                label={label}
                selected={selected}
                onToggle={() => {
                  const current = filters.cuisine ?? [];
                  patch({
                    cuisine: selected
                      ? current.filter((c) => c !== value)
                      : [...current, value],
                  });
                }}
              />
            );
          })}
        </div>
      </div>

      <div>
        <GroupLabel>Prep Method</GroupLabel>
        <div className="flex flex-wrap gap-2">
          {PREP_METHODS.map(({ value, label }) => (
            <FilterChip
              key={value}
              value={value}
              label={label}
              selected={filters.prep_method === value}
              onToggle={() =>
                patch({
                  prep_method:
                    filters.prep_method === value ? undefined : value,
                })
              }
            />
          ))}
        </div>
      </div>

      <div>
        <GroupLabel>Juice Color</GroupLabel>
        <div className="flex flex-wrap gap-2">
          {JUICE_COLORS.map((hex) => {
            const active = filters.color === hex;
            return (
              <button
                key={hex}
                type="button"
                aria-label={`Color ${hex}`}
                onClick={() => patch({ color: active ? undefined : hex })}
                className={cn(
                  "h-5 w-5 rounded-full border-2",
                  active ? "border-primary-dark" : "border-transparent",
                )}
                style={{ backgroundColor: hex }}
              />
            );
          })}
        </div>
      </div>

      <div>
        <GroupLabel>Max Calories</GroupLabel>
        <div className="flex max-w-[360px] items-center gap-3.5">
          <input
            type="range"
            min={200}
            max={1200}
            step={50}
            value={filters.max_calories ?? 800}
            onChange={(e) => patch({ max_calories: Number(e.target.value) })}
            className="h-1.5 flex-1 accent-primary"
          />
          <span className="min-w-16 font-mono text-[11px] text-primary">
            {filters.max_calories ?? 800} kcal
          </span>
        </div>
      </div>

      <div>
        <GroupLabel>Max Prep Time</GroupLabel>
        <div className="flex max-w-[360px] items-center gap-3.5">
          <input
            type="range"
            min={5}
            max={120}
            step={5}
            value={filters.max_prep_minutes ?? 45}
            onChange={(e) =>
              patch({ max_prep_minutes: Number(e.target.value) })
            }
            className="h-1.5 flex-1 accent-primary"
          />
          <span className="min-w-16 font-mono text-[11px] text-primary">
            {filters.max_prep_minutes ?? 45} min
          </span>
        </div>
      </div>

      <div>
        <GroupLabel>Source</GroupLabel>
        <div className="flex flex-wrap gap-2">
          {SOURCES.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => {
                // Source filter awaits API list support.
              }}
              className="rounded-pill border border-border bg-surface px-3.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.05em] text-text-muted"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
