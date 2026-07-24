import { cn } from "@/lib/utils";

interface RawCookedTagProps {
  type: "raw" | "cooked";
  className?: string;
}

const CONFIG = {
  raw: {
    label: "Raw",
    className: "bg-primary/15 text-primary-dark",
    dotClassName: "bg-primary",
  },
  cooked: {
    label: "Cooked",
    className: "bg-cta/15 text-[#a83440]",
    dotClassName: "bg-cta",
  },
} as const;

export function RawCookedTag({ type, className }: RawCookedTagProps) {
  const config = CONFIG[type];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill py-1 pl-2 pr-2.5 font-mono text-label uppercase tracking-[0.1em]",
        config.className,
        className,
      )}
    >
      <span
        className={cn("inline-block h-[7px] w-[7px] rounded-full", config.dotClassName)}
        aria-hidden
      />
      {config.label}
    </span>
  );
}
