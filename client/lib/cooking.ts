import type { CookingType, PrepMethod } from "@/lib/types";

export function toRawCookedTag(
  value: CookingType | PrepMethod | null | undefined,
): "raw" | "cooked" {
  if (!value) return "cooked";
  if (value === "raw" || value.startsWith("raw_")) return "raw";
  if (value === "juiced" || value === "blended" || value === "dehydrated" || value === "sprouted" || value === "fermented") {
    return "raw";
  }
  return "cooked";
}
