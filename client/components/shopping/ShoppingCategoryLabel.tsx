import { cn } from "@/lib/utils";

interface ShoppingCategoryLabelProps {
  category: string;
  className?: string;
}

export function ShoppingCategoryLabel({
  category,
  className,
}: ShoppingCategoryLabelProps) {
  return (
    <p
      className={cn(
        "mb-2.5 font-mono text-[11px] uppercase tracking-[0.14em] text-primary",
        className,
      )}
    >
      {category}
    </p>
  );
}
