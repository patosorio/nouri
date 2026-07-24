"use client";

import { cn } from "@/lib/utils";

interface ServingsAdjusterProps {
  value: number;
  onChange: (value: number) => void;
  className?: string;
}

export function ServingsAdjuster({
  value,
  onChange,
  className,
}: ServingsAdjusterProps) {
  return (
    <div
      className={cn(
        "mb-4 inline-flex items-center gap-3.5 rounded-pill border border-border bg-surface px-[18px] py-2 font-mono",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => onChange(Math.max(1, value - 1))}
        aria-label="Decrease servings"
        className="text-text"
      >
        −
      </button>
      <span className="min-w-4 text-center text-text">{value}</span>
      <button
        type="button"
        onClick={() => onChange(value + 1)}
        aria-label="Increase servings"
        className="text-text"
      >
        +
      </button>
    </div>
  );
}
