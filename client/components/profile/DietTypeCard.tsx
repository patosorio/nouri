import type { DietType } from "@/lib/types";
import { cn } from "@/lib/utils";

interface DietTypeCardProps {
  value: DietType;
  selected: boolean;
  onSelect: () => void;
  className?: string;
}

const LABELS: Record<DietType, { label: string; desc: string }> = {
  vegan: {
    label: "Vegan",
    desc: "No animal products at all",
  },
  plant_based: {
    label: "Plant-Based",
    desc: "Mostly plants, occasional flexibility",
  },
  wfpb: {
    label: "Whole Food Plant-Based",
    desc: "Plants, minimally processed",
  },
  pescatarian: {
    label: "Pescatarian",
    desc: "Plant-based plus fish and seafood",
  },
  flexitarian: {
    label: "Flexitarian",
    desc: "Mostly plants, occasional meat",
  },
  omnivore: {
    label: "Omnivore",
    desc: "All foods, plant-forward focus",
  },
  no_pork: {
    label: "No Pork",
    desc: "Everything except pork",
  },
};

export function DietTypeCard({
  value,
  selected,
  onSelect,
  className,
}: DietTypeCardProps) {
  const config = LABELS[value];
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex flex-col gap-1.5 rounded-card border-[1.5px] bg-surface px-5 py-[18px] text-left",
        selected
          ? "border-primary bg-primary/[0.06] shadow-[inset_0_0_0_1px_var(--color-primary)]"
          : "border-border",
        className,
      )}
    >
      <span className="font-sans text-title font-medium text-text">
        {config.label}
      </span>
      <span className="font-mono text-[10px] tracking-[0.02em] text-text-muted">
        {config.desc}
      </span>
    </button>
  );
}
