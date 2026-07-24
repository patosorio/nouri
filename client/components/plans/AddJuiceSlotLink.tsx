import { cn } from "@/lib/utils";

interface AddJuiceSlotLinkProps {
  onClick: () => void;
  disabled?: boolean;
  className?: string;
}

export function AddJuiceSlotLink({
  onClick,
  disabled,
  className,
}: AddJuiceSlotLinkProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "mt-2 font-mono text-xs text-primary disabled:opacity-40",
        className,
      )}
    >
      + Add juice slot
    </button>
  );
}
