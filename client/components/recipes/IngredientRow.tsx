import { cn } from "@/lib/utils";

interface IngredientRowProps {
  quantity: number;
  unit: string;
  ingredientName: string;
  notes?: string | null;
  className?: string;
}

export function IngredientRow({
  quantity,
  unit,
  ingredientName,
  notes,
  className,
}: IngredientRowProps) {
  return (
    <li
      className={cn(
        "flex items-baseline gap-3.5 border-b border-primary/10 py-2.5 last:border-0",
        className,
      )}
    >
      <span className="min-w-[76px] shrink-0 font-mono font-medium text-primary">
        {quantity} {unit}
      </span>
      <span className="font-sans text-[0.95rem] text-text">
        {ingredientName}
        {notes ? (
          <span className="italic text-text-muted">, {notes}</span>
        ) : null}
      </span>
    </li>
  );
}
