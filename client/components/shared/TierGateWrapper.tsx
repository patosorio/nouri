"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import { cn } from "@/lib/utils";

interface TierGateWrapperProps {
  /** Product language for the paid tier; maps to API/ERD tier `pro`. */
  requiredTier: "paid";
  children: ReactNode;
  fallback?: ReactNode;
  className?: string;
}

const DEFAULT_FALLBACK = (
  <div className="rounded-card border border-border bg-white/70 px-6 py-8 text-center">
    <p className="font-sans text-title font-semibold text-text-primary">
      Pro feature
    </p>
    <p className="mt-2 font-sans text-body-sm text-text-muted">
      Upgrade to Pro to unlock this feature.
    </p>
  </div>
);

export function TierGateWrapper({
  requiredTier,
  children,
  fallback = DEFAULT_FALLBACK,
  className,
}: TierGateWrapperProps) {
  const { tier, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className={cn("animate-pulse rounded-card bg-primary/10 p-8", className)} />
    );
  }

  // requiredTier "paid" ↔ ERD/API user_tier_enum "pro" (see missing.txt)
  const allowed = requiredTier === "paid" && tier === "pro";

  if (!allowed) {
    return <div className={className}>{fallback}</div>;
  }

  return <div className={className}>{children}</div>;
}
