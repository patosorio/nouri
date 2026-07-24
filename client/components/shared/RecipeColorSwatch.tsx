import { cn } from "@/lib/utils";

interface RecipeColorSwatchProps {
  color: string | null | undefined;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZES = {
  sm: "h-2.5 w-2.5",
  md: "h-3.5 w-3.5",
  lg: "h-4 w-4",
} as const;

export function RecipeColorSwatch({
  color,
  size = "md",
  className,
}: RecipeColorSwatchProps) {
  if (!color) {
    return (
      <span
        className={cn(
          "inline-block rounded-full border border-dashed border-primary/40",
          SIZES[size],
          className,
        )}
        aria-hidden
      />
    );
  }

  return (
    <span
      className={cn("inline-block rounded-full", SIZES[size], className)}
      style={{ backgroundColor: color }}
      aria-hidden
    />
  );
}
