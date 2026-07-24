import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface EyebrowLabelProps {
  children: ReactNode;
  size?: "sm" | "md";
  className?: string;
}

export function EyebrowLabel({
  children,
  size = "md",
  className,
}: EyebrowLabelProps) {
  return (
    <span
      className={cn(
        "font-mono uppercase tracking-[0.16em] text-primary",
        size === "sm" ? "text-eyebrow-sm" : "text-eyebrow",
        className,
      )}
    >
      {children}
    </span>
  );
}
