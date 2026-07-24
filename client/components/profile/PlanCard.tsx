import { cn } from "@/lib/utils";

interface PlanCardProps {
  tier: "free" | "paid";
  features: string[];
  className?: string;
}

export function PlanCard({ tier, features, className }: PlanCardProps) {
  return (
    <div
      className={cn(
        "rounded-card border border-border bg-surface p-6",
        className,
      )}
    >
      <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-primary">
        Current plan
      </p>
      <h3 className="mt-2 font-sans text-heading-lg font-semibold text-text">
        {tier === "paid" ? "Pro" : "Free"}
      </h3>
      <ul className="mt-4 space-y-2">
        {features.map((f) => (
          <li key={f} className="font-sans text-body-sm text-text-muted">
            · {f}
          </li>
        ))}
      </ul>
    </div>
  );
}
