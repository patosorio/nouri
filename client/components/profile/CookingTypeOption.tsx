import type { CookingType } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { CSSProperties } from "react";

interface CookingTypeOptionProps {
  value: CookingType;
  selected: boolean;
  onSelect: () => void;
  className?: string;
}

const OPTIONS: Record<
  CookingType,
  { label: string; barClassName: string; barStyle?: CSSProperties }
> = {
  raw_100: { label: "100% Raw", barClassName: "bg-primary" },
  raw_80_cooked_20: {
    label: "80/20 Raw-Cooked",
    barClassName: "",
    barStyle: {
      background:
        "linear-gradient(180deg, var(--color-primary) 80%, var(--color-cta) 80%)",
    },
  },
  raw_70_cooked_30: {
    label: "70/30 Raw-Cooked",
    barClassName: "",
    barStyle: {
      background:
        "linear-gradient(180deg, var(--color-primary) 70%, var(--color-cta) 70%)",
    },
  },
  raw_50_cooked_50: {
    label: "50/50",
    barClassName: "",
    barStyle: {
      background:
        "linear-gradient(180deg, var(--color-primary) 50%, var(--color-cta) 50%)",
    },
  },
  cooked_100: { label: "100% Cooked", barClassName: "bg-cta" },
};

export function CookingTypeOption({
  value,
  selected,
  onSelect,
  className,
}: CookingTypeOptionProps) {
  const config = OPTIONS[value];
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-4 rounded-xl border-[1.5px] bg-surface px-5 py-4 text-left",
        selected ? "border-primary bg-primary/[0.06]" : "border-border",
        className,
      )}
    >
      <span
        className={cn("h-9 w-1.5 shrink-0 rounded", config.barClassName)}
        style={config.barStyle}
        aria-hidden
      />
      <span className="font-sans text-body font-medium text-text">
        {config.label}
      </span>
    </button>
  );
}

export const COOKING_TYPE_VALUES = Object.keys(OPTIONS) as CookingType[];
