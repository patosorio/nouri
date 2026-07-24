"use client";

import { cn } from "@/lib/utils";

interface PantryAddBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  className?: string;
}

export function PantryAddBar({
  value,
  onChange,
  onSubmit,
  disabled,
  className,
}: PantryAddBarProps) {
  return (
    <form
      className={cn("flex gap-3", className)}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Add an ingredient…"
        className="max-w-md flex-1 rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none placeholder:text-text-muted focus:border-primary"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="rounded-pill bg-cta px-6 py-2.5 font-sans text-btn font-medium text-white hover:bg-[#db4750] disabled:opacity-50"
      >
        Add
      </button>
    </form>
  );
}
