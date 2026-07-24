"use client";

import { cn } from "@/lib/utils";

interface RecipeSearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function RecipeSearchInput({
  value,
  onChange,
  placeholder = 'Search recipes… e.g. "high-protein raw lunch"',
  className,
}: RecipeSearchInputProps) {
  return (
    <input
      type="search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      aria-label="Search recipes"
      className={cn(
        "w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none placeholder:text-text-muted focus:border-primary",
        className,
      )}
    />
  );
}
