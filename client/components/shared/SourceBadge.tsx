import type { SourceBadgeValue } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SourceBadgeProps {
  source: SourceBadgeValue | string;
  className?: string;
}

const CONFIG: Record<string, { label: string; className: string }> = {
  ai_generated: {
    label: "AI Generated",
    className: "bg-neutral/25 text-text-muted",
  },
  saved_recipe: {
    label: "From Your Recipes",
    className: "bg-primary/15 text-primary",
  },
  shared_corpus: {
    label: "Shared Corpus",
    className: "bg-primary/15 text-primary",
  },
  user_created: {
    label: "Yours",
    className: "bg-primary/15 text-primary",
  },
  imported: {
    label: "Imported",
    className: "bg-neutral/25 text-text-muted",
  },
};

export function SourceBadge({ source, className }: SourceBadgeProps) {
  const config = CONFIG[source] ?? {
    label: String(source).replaceAll("_", " "),
    className: "bg-neutral/25 text-text-muted",
  };

  return (
    <span
      className={cn(
        "inline-block rounded-pill px-2.5 py-0.5 font-mono text-label uppercase tracking-[0.08em]",
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  );
}
