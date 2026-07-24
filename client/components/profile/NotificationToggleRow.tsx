"use client";

import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

interface NotificationToggleRowProps {
  label: string;
  description?: string;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  className?: string;
}

export function NotificationToggleRow({
  label,
  description,
  enabled,
  onToggle,
  className,
}: NotificationToggleRowProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 border-b border-border py-4 last:border-0",
        className,
      )}
    >
      <div>
        <p className="m-0 font-sans font-medium text-text">{label}</p>
        {description ? (
          <p className="m-0 mt-1 font-sans text-body-sm text-text-muted">
            {description}
          </p>
        ) : null}
      </div>
      <Switch checked={enabled} onCheckedChange={onToggle} />
    </div>
  );
}
