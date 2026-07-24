"use client";

import type { PantryItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface PantryItemCardProps {
  item: PantryItem;
  category: string;
  onRemove: () => void;
  className?: string;
}

export function PantryItemCard({
  item,
  category,
  onRemove,
  className,
}: PantryItemCardProps) {
  const added = new Date(item.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  return (
    <div
      className={cn(
        "relative rounded-card border border-border bg-surface px-4 py-4",
        className,
      )}
    >
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${item.ingredient_name_raw}`}
        className="absolute right-3 top-2 border-0 bg-transparent text-lg text-text-muted"
      >
        ×
      </button>
      <p className="m-0 pr-6 font-sans font-medium text-text">
        {item.ingredient_name_raw}
      </p>
      <p className="mt-1.5 font-mono text-label uppercase tracking-[0.06em] text-text-muted">
        {category} · Added {added}
      </p>
    </div>
  );
}
