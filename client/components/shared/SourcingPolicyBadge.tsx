import type { RecipeUsagePolicy } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SourcingPolicyBadgeProps {
  policy: RecipeUsagePolicy;
  className?: string;
}

const LABELS: Record<RecipeUsagePolicy, string> = {
  prefer_saved: "Saved First",
  balanced: "Balanced",
  prefer_new: "Prefer New",
};

export function SourcingPolicyBadge({
  policy,
  className,
}: SourcingPolicyBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex whitespace-nowrap rounded-pill border border-neutral bg-white/10 px-4 py-1.5 font-mono text-eyebrow-sm uppercase tracking-[0.1em] text-neutral",
        className,
      )}
    >
      {LABELS[policy]}
    </span>
  );
}
