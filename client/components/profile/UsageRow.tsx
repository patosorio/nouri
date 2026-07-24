import { cn } from "@/lib/utils";

interface UsageRowProps {
  label: string;
  value: string;
  className?: string;
}

export function UsageRow({ label, value, className }: UsageRowProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between border-b border-border py-3 last:border-0",
        className,
      )}
    >
      <span className="font-sans text-body-sm text-text">{label}</span>
      <span className="font-mono text-[13px] text-primary">{value}</span>
    </div>
  );
}
