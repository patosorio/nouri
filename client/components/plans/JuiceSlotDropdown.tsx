import { cn } from "@/lib/utils";

interface JuiceSlotDropdownProps {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  className?: string;
  "aria-label"?: string;
}

export function JuiceSlotDropdown({
  value,
  onChange,
  options,
  className,
  "aria-label": ariaLabel,
}: JuiceSlotDropdownProps) {
  return (
    <select
      value={value}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "min-w-24 flex-1 rounded-lg border border-border bg-surface px-2.5 py-2 font-mono text-[11px] text-text outline-none focus:border-primary",
        className,
      )}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
