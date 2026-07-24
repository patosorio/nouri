"use client";

import { cn } from "@/lib/utils";

interface FilterChipProps {
  value: string;
  label: string;
  selected: boolean;
  onToggle: () => void;
  className?: string;
}

export function FilterChip({
  label,
  selected,
  onToggle,
  className,
}: FilterChipProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "shrink-0 whitespace-nowrap rounded-pill border px-3.5 py-[7px] font-mono text-[11px] font-normal tracking-[0.03em] transition-colors",
        selected
          ? "border-primary bg-primary text-white"
          : "border-border bg-surface text-text hover:border-primary/40",
        className,
      )}
    >
      {label}
    </button>
  );
}
