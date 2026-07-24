import { cn } from "@/lib/utils";

interface CuisineChipProps {
  label: string;
  selected: boolean;
  onToggle: () => void;
  className?: string;
}

export function CuisineChip({
  label,
  selected,
  onToggle,
  className,
}: CuisineChipProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "rounded-pill border px-[18px] py-3 font-mono text-xs tracking-[0.04em]",
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
