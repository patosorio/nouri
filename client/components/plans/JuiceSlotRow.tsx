import {
  JuiceColorDot,
  JUICE_COLOR_LABELS,
} from "@/components/plans/JuiceColorDot";
import type { JuiceColor, JuiceSize, JuiceTime } from "@/lib/types";
import { cn } from "@/lib/utils";

interface JuiceSlotRowProps {
  name: string;
  ingredients?: string;
  timeOfDay: JuiceTime;
  size: JuiceSize;
  color: JuiceColor;
  className?: string;
}

const TIME_LABEL: Record<JuiceTime, string> = {
  morning: "Morning",
  pre_lunch: "Pre-lunch",
  lunch: "Lunch",
  afternoon: "Afternoon",
  evening: "Evening",
  dinner: "Dinner",
  after_dinner: "After Dinner",
};

const SIZE_META: Record<JuiceSize, string> = {
  shot_ml125: "Shot · 125 ml",
  oz8_ml250: "8 oz · 250 ml",
  oz16_ml500: "16 oz · 500 ml",
  oz24_ml750: "24 oz · 750 ml",
  oz32_ml1000: "32 oz · 1 L",
};

export function JuiceSlotRow({
  name,
  ingredients,
  timeOfDay,
  size,
  color,
  className,
}: JuiceSlotRowProps) {
  const meta = [
    TIME_LABEL[timeOfDay],
    JUICE_COLOR_LABELS[color],
    SIZE_META[size],
  ]
    .join(" · ")
    .toUpperCase();

  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3.5 rounded-r-card border border-l-[3px] border-border border-l-primary bg-surface py-3.5 pl-[18px] pr-[18px]",
        className,
      )}
    >
      <div className="min-w-0">
        <p className="m-0 flex items-center gap-2 font-sans font-medium text-text">
          <JuiceColorDot color={color} className="h-2.5 w-2.5" />
          {name}
        </p>
        {ingredients ? (
          <p className="mt-1 truncate font-mono text-eyebrow-sm uppercase tracking-[0.04em] text-text-muted">
            {ingredients}
          </p>
        ) : null}
      </div>
      <span className="shrink-0 whitespace-nowrap font-mono text-eyebrow-sm uppercase text-text-muted">
        {meta}
      </span>
    </div>
  );
}
