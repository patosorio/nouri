import Link from "next/link";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import type { PantryItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface PantrySummaryPanelProps {
  items: PantryItem[];
  className?: string;
}

export function PantrySummaryPanel({
  items,
  className,
}: PantrySummaryPanelProps) {
  return (
    <aside
      className={cn(
        "w-full shrink-0 self-start rounded-card border border-border bg-surface p-6 lg:w-80",
        className,
      )}
    >
      <EyebrowLabel>Your Pantry</EyebrowLabel>
      <p className="mt-2.5 font-sans text-body-sm text-text-muted">
        Items you check off are automatically added here.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {items.length === 0 ? (
          <p className="font-sans text-body-sm italic text-text-muted">
            Pantry is empty.
          </p>
        ) : (
          items.slice(0, 12).map((item) => (
            <span
              key={item.id}
              className="rounded-pill bg-neutral/20 px-3 py-1.5 font-mono text-[11px] text-text-muted"
            >
              {item.ingredient_name_raw}
            </span>
          ))
        )}
      </div>
      <Link
        href="/pantry"
        className="mt-4 inline-block font-mono text-xs text-primary no-underline"
      >
        View Full Pantry →
      </Link>
    </aside>
  );
}
