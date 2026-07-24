import { RawCookedTag } from "@/components/shared/RawCookedTag";
import { toRawCookedTag } from "@/lib/cooking";
import type { PlanItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface CalendarWeekPreviewProps {
  items: PlanItem[];
  className?: string;
}

export function CalendarWeekPreview({
  items,
  className,
}: CalendarWeekPreviewProps) {
  const meals = items.filter((item) => item.slot !== "juice").slice(0, 3);

  if (meals.length === 0) return null;

  return (
    <div
      className={cn(
        "mb-4 mt-0 flex flex-wrap gap-3.5 rounded-xl border border-border bg-surface px-5 py-4",
        className,
      )}
    >
      {meals.map((item) => (
        <div
          key={item.id}
          className="flex items-center gap-2 font-sans text-[0.9rem] text-text"
        >
          <RawCookedTag type={toRawCookedTag(item.prep_method)} />
          <span>{item.name}</span>
        </div>
      ))}
    </div>
  );
}
