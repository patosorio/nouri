"use client";

import { cn } from "@/lib/utils";

interface PurchasedDisclosureProps {
  count: number;
  expanded: boolean;
  onToggle: () => void;
  className?: string;
}

export function PurchasedDisclosure({
  count,
  expanded,
  onToggle,
  className,
}: PurchasedDisclosureProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "py-2 font-mono text-[11px] tracking-[0.06em] text-primary",
        className,
      )}
    >
      Already purchased ({count} items) {expanded ? "▴" : "▾"}
    </button>
  );
}
