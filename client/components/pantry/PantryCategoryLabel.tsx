import { cn } from "@/lib/utils";

interface PantryCategoryLabelProps {
  category: string;
  className?: string;
}

export function PantryCategoryLabel({
  category,
  className,
}: PantryCategoryLabelProps) {
  return (
    <p
      className={cn(
        "mb-3 mt-8 font-mono text-[11px] uppercase tracking-[0.14em] text-primary first:mt-0",
        className,
      )}
    >
      {category}
    </p>
  );
}
