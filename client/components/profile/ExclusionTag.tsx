"use client";

import { cn } from "@/lib/utils";

interface ExclusionTagProps {
  name: string;
  onRemove: () => void;
  className?: string;
}

export function ExclusionTag({ name, onRemove, className }: ExclusionTagProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-pill bg-primary-dark py-1.5 pl-3.5 pr-2 font-mono text-[11px] text-white",
        className,
      )}
    >
      {name}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${name}`}
        className="border-0 bg-transparent px-1 text-white/80"
      >
        ×
      </button>
    </span>
  );
}
