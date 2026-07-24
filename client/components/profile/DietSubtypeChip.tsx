import { cn } from "@/lib/utils";

interface DietSubtypeChipProps {
  label: string;
  selected: boolean;
  onToggle: () => void;
  className?: string;
}

export function DietSubtypeChip({
  label,
  selected,
  onToggle,
  className,
}: DietSubtypeChipProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "rounded-pill border px-[18px] py-[9px] font-mono text-[11px] tracking-[0.04em]",
        selected
          ? "border-primary bg-primary text-white"
          : "border-border bg-surface text-text",
        className,
      )}
    >
      {label}
    </button>
  );
}
