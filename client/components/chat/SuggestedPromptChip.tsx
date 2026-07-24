"use client";

import { cn } from "@/lib/utils";

interface SuggestedPromptChipProps {
  label: string;
  onClick: () => void;
  className?: string;
}

export function SuggestedPromptChip({
  label,
  onClick,
  className,
}: SuggestedPromptChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-pill border border-primary/25 bg-primary/10 px-4 py-2 font-mono text-eyebrow tracking-[0.04em] text-primary",
        className,
      )}
    >
      {label}
    </button>
  );
}
