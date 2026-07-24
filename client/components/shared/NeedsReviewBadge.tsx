import { cn } from "@/lib/utils";

interface NeedsReviewBadgeProps {
  className?: string;
}

export function NeedsReviewBadge({ className }: NeedsReviewBadgeProps) {
  return (
    <span
      className={cn(
        "inline-block rounded-pill bg-cta/15 px-2.5 py-0.5 font-mono text-label uppercase tracking-[0.08em] text-[#a83440]",
        className,
      )}
    >
      Needs Review
    </span>
  );
}
