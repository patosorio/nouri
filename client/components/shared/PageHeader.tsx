import type { ReactNode } from "react";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  eyebrow: string;
  title: string;
  description?: string;
  /** Right-side actions (buttons). Same vertical align as meal plans. */
  actions?: ReactNode;
  className?: string;
  /** Heading level — profile subsections use h2. */
  as?: "h1" | "h2";
}

/**
 * Shared page title block. Do not re-implement eyebrow/title/subtitle per route.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
  as = "h1",
}: PageHeaderProps) {
  const Heading = as;

  return (
    <div
      className={cn(
        "mb-8 flex flex-wrap items-start justify-between gap-4",
        className,
      )}
    >
      <div className="min-w-0">
        <EyebrowLabel>{eyebrow}</EyebrowLabel>
        <Heading className="mt-2 font-sans text-heading font-medium text-text">
          {title}
        </Heading>
        {description ? (
          <p className="mt-1 font-sans text-body-sm italic text-text-muted">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-3">{actions}</div>
      ) : null}
    </div>
  );
}
