import { cn } from "@/lib/utils";

interface SkipLinkProps {
  label: string;
  onClick: () => void;
  className?: string;
}

export function SkipLink({ label, onClick, className }: SkipLinkProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "font-mono text-xs text-text-muted underline",
        className,
      )}
    >
      {label}
    </button>
  );
}
