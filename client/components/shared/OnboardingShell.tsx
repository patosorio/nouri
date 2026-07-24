import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface OnboardingShellProps {
  children: ReactNode;
  className?: string;
}

export function OnboardingShell({ children, className }: OnboardingShellProps) {
  return (
    <div
      className={cn(
        "relative z-[1] mx-auto w-full max-w-[640px] px-8 pb-24 pt-16",
        className,
      )}
    >
      {children}
    </div>
  );
}
