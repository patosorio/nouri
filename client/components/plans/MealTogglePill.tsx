import { cn } from "@/lib/utils";

type MealSlot = "breakfast" | "lunch" | "dinner";

interface MealTogglePillProps {
  slot: MealSlot;
  active: boolean;
  onToggle: () => void;
  className?: string;
}

const LABELS: Record<MealSlot, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
};

export function MealTogglePill({
  slot,
  active,
  onToggle,
  className,
}: MealTogglePillProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "flex-1 rounded-pill border px-3.5 py-[9px] text-center font-mono text-[11px] tracking-[0.04em]",
        active
          ? "border-primary bg-primary text-white"
          : "border-border bg-surface text-text-muted",
        className,
      )}
    >
      {LABELS[slot]}
    </button>
  );
}
