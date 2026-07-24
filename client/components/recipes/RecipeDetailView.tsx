"use client";

import { useMemo, useState } from "react";
import { IngredientRow } from "@/components/recipes/IngredientRow";
import { ServingsAdjuster } from "@/components/recipes/ServingsAdjuster";
import { StepRow } from "@/components/recipes/StepRow";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { NutritionStrip } from "@/components/shared/NutritionStrip";
import { RawCookedTag } from "@/components/shared/RawCookedTag";
import { SourceBadge } from "@/components/shared/SourceBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecipe } from "@/hooks";
import { apiClient } from "@/lib/api-client";
import { toRawCookedTag } from "@/lib/cooking";
import type { NutritionalProfile } from "@/lib/types";

interface RecipeDetailViewProps {
  recipeId: string;
}

function splitTitle(name: string): { lead: string; emphasis: string | null } {
  const parts = name.split(/\s+/);
  if (parts.length < 3) return { lead: name, emphasis: null };
  const mid = Math.floor(parts.length / 2);
  return {
    lead: parts.slice(0, mid).join(" "),
    emphasis: parts.slice(mid).join(" "),
  };
}

export function RecipeDetailView({ recipeId }: RecipeDetailViewProps) {
  const { data: recipe, isLoading, isError } = useRecipe(recipeId);
  const [servings, setServings] = useState<number | null>(null);
  const [profile, setProfile] = useState<NutritionalProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);

  const effectiveServings = servings ?? recipe?.servings ?? 1;
  const scale = recipe ? effectiveServings / recipe.servings : 1;

  const scaledIngredients = useMemo(() => {
    if (!recipe) return [];
    return recipe.ingredients.map((ing) => ({
      ...ing,
      amount: Math.round(ing.amount * scale * 100) / 100,
    }));
  }, [recipe, scale]);

  async function loadNutritionProfile() {
    setProfileLoading(true);
    try {
      const result = await apiClient.getRecipeNutritionProfile(recipeId);
      setProfile(result);
    } catch {
      setProfile(null);
    } finally {
      setProfileLoading(false);
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4 p-10">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-56 w-full" />
      </div>
    );
  }

  if (isError || !recipe) {
    return (
      <div className="p-10">
        <p className="font-sans text-body text-cta">Recipe not found.</p>
      </div>
    );
  }

  const nutrition = recipe.nutrition;
  const title = splitTitle(recipe.name);
  const meta = [
    recipe.cooking_type?.replaceAll("_", " "),
    recipe.prep_minutes != null ? `Prep ${recipe.prep_minutes} min` : null,
    `Serves ${recipe.servings}`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="flex-1 overflow-y-auto px-8 py-10 lg:px-14">
      <div className="grid grid-cols-1 items-start gap-10 lg:grid-cols-[1.35fr_1fr] lg:gap-14">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2.5">
            <EyebrowLabel>Your Recipe</EyebrowLabel>
            <SourceBadge source={recipe.source} />
          </div>

          <h1 className="font-sans text-heading-lg font-medium text-text">
            {title.emphasis ? (
              <>
                {title.lead} <em>{title.emphasis}</em>
              </>
            ) : (
              recipe.name
            )}
          </h1>

          {recipe.description ? (
            <p className="mt-2.5 max-w-[520px] font-sans text-body italic text-text-muted">
              {recipe.description}
            </p>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center gap-3.5">
            <RawCookedTag type={toRawCookedTag(recipe.cooking_type)} />
            {meta ? (
              <span className="font-mono text-eyebrow-sm tracking-[0.06em] text-text-muted">
                {meta}
              </span>
            ) : null}
          </div>

          {recipe.diet_subtypes?.length ? (
            <div className="mt-6 flex flex-wrap gap-2">
              {recipe.diet_subtypes.map((subtype) => (
                <span
                  key={subtype}
                  className="rounded-pill border border-border bg-surface px-3.5 py-1.5 font-mono text-eyebrow tracking-[0.04em] text-text"
                >
                  {subtype.replaceAll("_", " ")}
                </span>
              ))}
            </div>
          ) : null}

          <div className="my-7 h-px bg-border" />

          <EyebrowLabel>Ingredients</EyebrowLabel>
          <div className="mt-4">
            <ServingsAdjuster
              value={effectiveServings}
              onChange={setServings}
            />
          </div>
          <ul className="mt-4">
            {scaledIngredients.map((ing, idx) => (
              <IngredientRow
                key={ing.id ?? `${ing.ingredient_id}-${idx}`}
                quantity={ing.amount}
                unit={ing.unit}
                ingredientName={ing.ingredient_name ?? "Ingredient"}
                notes={ing.notes}
              />
            ))}
          </ul>

          <div className="my-7 h-px bg-border" />

          <EyebrowLabel>Method</EyebrowLabel>
          <ol className="mt-2">
            {recipe.steps.map((step) => (
              <StepRow
                key={step.step_number}
                stepNumber={step.step_number}
                instruction={step.instruction}
                durationMinutes={step.duration_minutes}
                tips={step.tips}
              />
            ))}
          </ol>

          <div className="mt-8 flex flex-wrap gap-3">
            <button
              type="button"
              className="btn-ghost"
            >
              Edit Recipe
            </button>
            <button
              type="button"
              className="btn-ghost"
            >
              Export PDF
            </button>
            <button
              type="button"
              className="btn-ghost"
            >
              Add to Plan
            </button>
            <button
              type="button"
              className="btn-ghost"
            >
              Riff on This
            </button>
          </div>
        </div>

        <div>
          <div className="mb-5 h-[300px] rounded-card bg-gradient-to-br from-primary/25 to-highlight/30" />

          {nutrition ? (
            <NutritionStrip
              vertical
              title="Nutrition · Per Serving"
              calories={nutrition.calories_per_serving}
              proteinG={nutrition.protein_g}
              carbsG={nutrition.carbs_g}
              fatG={nutrition.fat_g}
              fiberG={nutrition.fiber_g}
              footer={
                <p className="mt-4 border-t border-white/15 pt-3 font-mono text-[10.5px] leading-relaxed tracking-[0.01em] text-white/65">
                  AI-estimated values — for educational guidance only, not a
                  substitute for clinical nutrition advice.
                </p>
              }
            />
          ) : null}

          <button
            type="button"
            onClick={() => void loadNutritionProfile()}
            disabled={profileLoading}
            className="mt-4 w-full btn-ghost disabled:opacity-50"
          >
            {profileLoading
              ? "Loading…"
              : "Get Full Nutritional Profile"}
          </button>

          {profile ? (
            <div className="mt-4 space-y-2 rounded-card border border-border bg-surface p-4">
              {profile.per_serving.nutritional_highlights?.map((h) => (
                <p key={h.nutrient} className="font-sans text-body-sm">
                  <span className="font-medium text-text">{h.nutrient}:</span>{" "}
                  <span className="text-text-muted">{h.note}</span>
                </p>
              ))}
              {profile.per_serving.food_advisor_notes ? (
                <p className="font-sans text-body-sm italic text-text-muted">
                  {profile.per_serving.food_advisor_notes}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
