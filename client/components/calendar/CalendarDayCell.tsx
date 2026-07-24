import { cn } from "@/lib/utils";

interface CalendarDayCellProps {
  dayNumber: number;
  isOutsideMonth?: boolean;
  isPastWeek?: boolean;
  className?: string;
}

export function CalendarDayCell({
  dayNumber,
  isOutsideMonth = false,
  isPastWeek = false,
  className,
}: CalendarDayCellProps) {
  return (
    <div
      className={cn(
        "min-h-16 rounded-lg border border-border bg-surface p-2 font-mono text-[11px] text-text-muted",
        isOutsideMonth && "opacity-40",
        isPastWeek && "opacity-50",
        className,
      )}
    >
      {dayNumber}
    </div>
  );
}
