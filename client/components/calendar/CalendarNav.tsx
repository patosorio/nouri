"use client";

import { cn } from "@/lib/utils";

interface CalendarNavProps {
  monthLabel: string;
  onPrev: () => void;
  onNext: () => void;
  className?: string;
}

export function CalendarNav({
  monthLabel,
  onPrev,
  onNext,
  className,
}: CalendarNavProps) {
  return (
    <div
      className={cn(
        "mb-5 flex items-center gap-4 font-mono text-[13px] text-primary",
        className,
      )}
    >
      <button
        type="button"
        onClick={onPrev}
        aria-label="Previous month"
        className="border-0 bg-transparent text-base text-primary"
      >
        ←
      </button>
      <span>{monthLabel}</span>
      <button
        type="button"
        onClick={onNext}
        aria-label="Next month"
        className="border-0 bg-transparent text-base text-primary"
      >
        →
      </button>
    </div>
  );
}
