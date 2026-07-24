import type { RecipeType } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RecipeTypeBadgeProps {
  type: RecipeType | string;
  className?: string;
}

const CONFIG: Record<string, { label: string; className: string }> = {
  meal: {
    label: "Meal",
    className: "bg-primary/15 text-primary-dark",
  },
  juice: {
    label: "Juice",
    className: "bg-primary/20 text-primary-dark",
  },
  smoothie: {
    label: "Smoothie",
    className: "bg-cta/15 text-[#a83440]",
  },
};

export function RecipeTypeBadge({ type, className }: RecipeTypeBadgeProps) {
  const config = CONFIG[type] ?? {
    label: String(type),
    className: "bg-primary/15 text-primary-dark",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-pill px-2.5 py-1 font-mono text-label uppercase",
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  );
}
