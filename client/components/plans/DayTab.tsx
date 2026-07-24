"use client";

import { cn } from "@/lib/utils";

interface DayTabProps {
  label: string;
  active: boolean;
  onSelect: () => void;
  className?: string;
}

export function DayTab({ label, active, onSelect, className }: DayTabProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "rounded-pill px-5 py-2.5 font-mono text-eyebrow uppercase tracking-[0.1em]",
        active
          ? "bg-primary text-white"
          : "bg-transparent text-text-muted hover:text-text",
        className,
      )}
    >
      {label}
    </button>
  );
}
