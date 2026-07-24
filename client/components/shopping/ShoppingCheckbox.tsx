"use client";

import { cn } from "@/lib/utils";

interface ShoppingCheckboxProps {
  checked: boolean;
  onToggle: () => void;
  className?: string;
}

export function ShoppingCheckbox({
  checked,
  onToggle,
  className,
}: ShoppingCheckboxProps) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={onToggle}
      className={cn(
        "flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] border-[1.5px] text-[11px] text-white",
        checked
          ? "border-primary bg-primary"
          : "border-border bg-surface",
        className,
      )}
    >
      {checked ? "✓" : null}
    </button>
  );
}
