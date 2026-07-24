import type { JuiceColor } from "@/lib/types";
import { cn } from "@/lib/utils";

interface JuiceColorDotProps {
  color: JuiceColor;
  className?: string;
}

const COLOR_CLASS: Record<JuiceColor, string> = {
  purple: "bg-[#8E6FD1]",
  green: "bg-[#6FCF7B]",
  yellow: "bg-[#F3E751]",
  orange: "bg-[#F4A261]",
  red: "bg-[#F45B63]",
  pink: "bg-[#E89AB3]",
  blue: "bg-[#4980DA]",
};

export function JuiceColorDot({ color, className }: JuiceColorDotProps) {
  return (
    <span
      className={cn(
        "inline-block h-3 w-3 shrink-0 rounded-full",
        COLOR_CLASS[color],
        className,
      )}
      aria-hidden
    />
  );
}

export const JUICE_COLOR_LABELS: Record<JuiceColor, string> = {
  purple: "Purple",
  green: "Green",
  yellow: "Yellow",
  orange: "Orange",
  red: "Red",
  pink: "Pink",
  blue: "Blue",
};
