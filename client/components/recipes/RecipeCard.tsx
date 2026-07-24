import Link from "next/link";
import { RawCookedTag } from "@/components/shared/RawCookedTag";
import { RecipeColorSwatch } from "@/components/shared/RecipeColorSwatch";
import { RecipeTypeBadge } from "@/components/shared/RecipeTypeBadge";
import { toRawCookedTag } from "@/lib/cooking";
import type { RecipeListItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RecipeCardProps {
  recipe: RecipeListItem;
  className?: string;
}

export function RecipeCard({ recipe, className }: RecipeCardProps) {
  return (
    <Link
      href={`/recipes/${recipe.id}`}
      className={cn(
        "group block overflow-hidden rounded-card border border-border bg-surface transition-colors hover:border-primary/40",
        className,
      )}
    >
      <div className="relative h-40 bg-gradient-to-br from-primary/25 to-highlight/30">
        <div className="absolute left-3 top-3">
          <RecipeColorSwatch color={recipe.color} size="lg" />
        </div>
      </div>
      <div className="space-y-2 p-4">
        <div className="flex flex-wrap gap-2">
          <RecipeTypeBadge type={recipe.recipe_type} />
          <RawCookedTag type={toRawCookedTag(recipe.cooking_type)} />
        </div>
        <h3 className="font-sans text-title font-medium text-text group-hover:text-primary-dark">
          {recipe.name}
        </h3>
        {recipe.description ? (
          <p className="line-clamp-2 font-sans text-body-sm italic text-text-muted">
            {recipe.description}
          </p>
        ) : null}
      </div>
    </Link>
  );
}
