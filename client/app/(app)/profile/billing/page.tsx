"use client";

import { PlanCard } from "@/components/profile/PlanCard";
import { UsageRow } from "@/components/profile/UsageRow";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { Skeleton } from "@/components/ui/skeleton";
import { useProfile } from "@/hooks";

export default function ProfileBillingPage() {
  const { data: profile, isLoading } = useProfile();

  if (isLoading || !profile) {
    return <Skeleton className="h-64 w-full max-w-md" />;
  }

  const isPaid = profile.tier === "pro";

  return (
    <section>
      <EyebrowLabel>Billing</EyebrowLabel>
      <h2 className="mt-2 mb-6 font-sans text-title font-semibold text-text">
        Plan & usage
      </h2>

      <PlanCard
        tier={isPaid ? "paid" : "free"}
        features={
          isPaid
            ? [
                "Unlimited plan generations",
                "Pantry tracking",
                "Priority recipe search",
              ]
            : [
                "Limited plan generations",
                "Core meal planning",
                "Recipe library",
              ]
        }
        className="mb-6 max-w-md"
      />

      <div className="mb-6 max-w-md rounded-card border border-border bg-surface px-5 py-2">
        <UsageRow
          label="Generation credits remaining"
          value={String(profile.generation_credits_remaining)}
        />
        <UsageRow label="Tier" value={isPaid ? "Pro" : "Free"} />
      </div>

      {!isPaid ? (
        <button
          type="button"
          className="btn-primary"
        >
          Upgrade to Pro
        </button>
      ) : null}
    </section>
  );
}
