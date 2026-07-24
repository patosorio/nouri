"use client";

import { ShoppingCheckbox } from "@/components/shopping/ShoppingCheckbox";
import type { ShoppingListItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ShoppingItemRowProps {
  item: ShoppingListItem;
  checked: boolean;
  onToggle: () => void;
  className?: string;
}

export function ShoppingItemRow({
  item,
  checked,
  onToggle,
  className,
}: ShoppingItemRowProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 py-2.5",
        checked && "opacity-55",
        className,
      )}
    >
      <ShoppingCheckbox checked={checked} onToggle={onToggle} />
      <span className="min-w-16 shrink-0 font-mono font-medium text-primary">
        {item.quantity_total} {item.unit}
      </span>
      <span
        className={cn(
          "font-sans text-[0.95rem] text-text",
          checked && "line-through",
        )}
      >
        {item.ingredient_name_display}
      </span>
    </div>
  );
}
