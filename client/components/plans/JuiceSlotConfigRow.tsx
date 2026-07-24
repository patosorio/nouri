import {
  JuiceColorDot,
  JUICE_COLOR_LABELS,
} from "@/components/plans/JuiceColorDot";
import { JuiceSlotDropdown } from "@/components/plans/JuiceSlotDropdown";
import type { JuiceColor, JuiceSize, JuiceTime } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface JuiceSlotDraft {
  id: string;
  time: JuiceTime;
  color: JuiceColor;
  size: JuiceSize;
}

interface JuiceSlotConfigRowProps {
  slot: JuiceSlotDraft;
  onChange: (slot: JuiceSlotDraft) => void;
  onRemove: () => void;
  className?: string;
}

const TIME_OPTIONS: { value: JuiceTime; label: string }[] = [
  { value: "morning", label: "Morning" },
  { value: "pre_lunch", label: "Pre-lunch" },
  { value: "afternoon", label: "Afternoon" },
  { value: "evening", label: "Evening" },
];

const SIZE_OPTIONS: { value: JuiceSize; label: string }[] = [
  { value: "shot_ml125", label: "Shot — 125 ml" },
  { value: "oz8_ml250", label: "8 oz — 250 ml" },
  { value: "oz16_ml500", label: "16 oz — 500 ml" },
  { value: "oz24_ml750", label: "24 oz — 750 ml" },
  { value: "oz32_ml1000", label: "32 oz — 1 L" },
];

const COLOR_OPTIONS = (
  Object.keys(JUICE_COLOR_LABELS) as JuiceColor[]
).map((value) => ({
  value,
  label: JUICE_COLOR_LABELS[value],
}));

export function JuiceSlotConfigRow({
  slot,
  onChange,
  onRemove,
  className,
}: JuiceSlotConfigRowProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2",
        className,
      )}
    >
      <JuiceSlotDropdown
        aria-label="Juice time of day"
        value={slot.time}
        options={TIME_OPTIONS}
        onChange={(time) =>
          onChange({ ...slot, time: time as JuiceTime })
        }
      />
      <div className="relative min-w-24 flex-1">
        <div className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center">
          <JuiceColorDot color={slot.color} />
        </div>
        <select
          aria-label="Juice color"
          value={slot.color}
          onChange={(e) =>
            onChange({ ...slot, color: e.target.value as JuiceColor })
          }
          className="w-full appearance-none rounded-lg border border-border bg-surface py-2 pl-8 pr-7 font-mono text-[11px] text-text outline-none focus:border-primary"
        >
          {COLOR_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <span className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center font-mono text-[9px] text-text-muted">
          ▾
        </span>
      </div>
      <JuiceSlotDropdown
        aria-label="Juice size"
        value={slot.size}
        options={SIZE_OPTIONS}
        onChange={(size) =>
          onChange({ ...slot, size: size as JuiceSize })
        }
      />
      <button
        type="button"
        onClick={onRemove}
        aria-label="Remove juice slot"
        className="shrink-0 px-1 text-base text-text-muted"
      >
        ×
      </button>
    </div>
  );
}
