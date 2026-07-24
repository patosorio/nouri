"use client";

import { useEffect, useState } from "react";
import { CookingTypeOption, COOKING_TYPE_VALUES } from "@/components/profile/CookingTypeOption";
import { CuisineChip } from "@/components/profile/CuisineChip";
import { DietSubtypeChip } from "@/components/profile/DietSubtypeChip";
import { DietTypeCard } from "@/components/profile/DietTypeCard";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { Skeleton } from "@/components/ui/skeleton";
import { useProfile, useUpdateProfile } from "@/hooks";
import type { CookingType, DietType } from "@/lib/types";

const DIET_TYPES: DietType[] = [
  "plant_based",
  "vegan",
  "wfpb",
  "pescatarian",
  "flexitarian",
  "omnivore",
  "no_pork",
];

const SUBTYPES = [
  "Keto",
  "High Protein",
  "Low Carb",
  "High Fiber",
  "Detox",
  "Anti-Inflammatory",
];

const CUISINES = [
  "Mediterranean",
  "Italian",
  "Asian",
  "Indian",
  "Middle Eastern",
  "Mexican",
  "Japanese",
  "Thai",
];

export default function ProfileDietPage() {
  const { data: profile, isLoading } = useProfile();
  const update = useUpdateProfile();
  const [dietType, setDietType] = useState<DietType>("plant_based");
  const [cookingType, setCookingType] =
    useState<CookingType>("raw_80_cooked_20");
  const [subtypes, setSubtypes] = useState<string[]>([]);
  const [cuisines, setCuisines] = useState<string[]>([]);
  const [calorieTarget, setCalorieTarget] = useState(2050);

  useEffect(() => {
    if (!profile) return;
    setDietType(profile.diet_type);
    setCookingType(profile.cooking_type);
    setSubtypes(profile.diet_subtypes);
    setCuisines(profile.cuisine_prefs);
    setCalorieTarget(profile.calorie_target ?? 2050);
  }, [profile]);

  if (isLoading || !profile) {
    return <Skeleton className="h-96 w-full" />;
  }

  async function handleSave() {
    await update.mutateAsync({
      diet_type: dietType,
      cooking_type: cookingType,
      diet_subtypes: subtypes,
      cuisine_prefs: cuisines,
      calorie_target: calorieTarget,
    });
  }

  return (
    <section>
      <EyebrowLabel>Diet Preferences</EyebrowLabel>
      <h2 className="mt-2 mb-6 font-sans text-title font-semibold text-text">
        How you eat
      </h2>

      <div className="mb-8">
        <p className="mb-3.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Diet Type
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {DIET_TYPES.map((value) => (
            <DietTypeCard
              key={value}
              value={value}
              selected={dietType === value}
              onSelect={() => setDietType(value)}
            />
          ))}
        </div>
      </div>

      <div className="mb-8">
        <p className="mb-3.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Cooking Type
        </p>
        <div className="flex max-w-lg flex-col gap-2.5">
          {COOKING_TYPE_VALUES.map((value) => (
            <CookingTypeOption
              key={value}
              value={value}
              selected={cookingType === value}
              onSelect={() => setCookingType(value)}
            />
          ))}
        </div>
      </div>

      <div className="mb-8">
        <p className="mb-3.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Diet Subtypes
        </p>
        <div className="flex flex-wrap gap-2">
          {SUBTYPES.map((label) => (
            <DietSubtypeChip
              key={label}
              label={label}
              selected={subtypes.includes(label)}
              onToggle={() =>
                setSubtypes((prev) =>
                  prev.includes(label)
                    ? prev.filter((s) => s !== label)
                    : [...prev, label],
                )
              }
            />
          ))}
        </div>
      </div>

      <div className="mb-8">
        <p className="mb-3.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Cuisine
        </p>
        <div className="flex flex-wrap gap-2">
          {CUISINES.map((label) => (
            <CuisineChip
              key={label}
              label={label}
              selected={cuisines.includes(label)}
              onToggle={() =>
                setCuisines((prev) =>
                  prev.includes(label)
                    ? prev.filter((c) => c !== label)
                    : [...prev, label],
                )
              }
            />
          ))}
        </div>
      </div>

      <div className="mb-8 max-w-xs">
        <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Daily Calorie Target
        </p>
        <input
          type="number"
          value={calorieTarget}
          onChange={(e) => setCalorieTarget(Number(e.target.value))}
          className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none focus:border-primary"
        />
      </div>

      <button
        type="button"
        onClick={() => void handleSave()}
        disabled={update.isPending}
        className="btn-primary disabled:opacity-50"
      >
        {update.isPending ? "Saving…" : "Save Preferences"}
      </button>
    </section>
  );
}
