import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PageShellProps {
  children: ReactNode;
  className?: string;
  /** Wider content row (e.g. calendar + side card). */
  wide?: boolean;
}

/**
 * Single page chrome for all (app) routes — padding/margins live here only.
 * Reference: meal plans library header (screen density + px-8 py-8).
 */
export function PageShell({ children, className, wide = false }: PageShellProps) {
  return (
    <div
      className={cn(
        "flex-1 overflow-y-auto px-8 py-8",
        wide && "lg:px-10",
        className,
      )}
    >
      {children}
    </div>
  );
}
