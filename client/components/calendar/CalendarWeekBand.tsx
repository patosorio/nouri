import { cn } from "@/lib/utils";

interface CalendarWeekBandProps {
  planTitle: string;
  className?: string;
}

export function CalendarWeekBand({ planTitle, className }: CalendarWeekBandProps) {
  return (
    <div
      className={cn(
        "pointer-events-none absolute left-2 right-2 top-[34px] flex h-[26px] items-center rounded-md bg-primary-dark px-3 font-sans text-xs font-medium text-white",
        className,
      )}
    >
      {planTitle}
    </div>
  );
}
