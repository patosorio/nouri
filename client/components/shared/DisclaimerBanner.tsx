import { cn } from "@/lib/utils";

const DISCLAIMER_COPY =
  "Nutritional values are AI-estimated and indicative only. Not medical or clinical nutrition advice.";

interface DisclaimerBannerProps {
  className?: string;
}

export function DisclaimerBanner({ className }: DisclaimerBannerProps) {
  return (
    <aside
      role="note"
      className={cn(
        "rounded-card border border-border bg-white/60 px-4 py-3 font-mono text-eyebrow-sm text-text-muted",
        className,
      )}
    >
      {DISCLAIMER_COPY}
    </aside>
  );
}
