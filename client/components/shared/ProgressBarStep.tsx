import { cn } from "@/lib/utils";

interface ProgressBarStepProps {
  currentStep: number;
  totalSteps: number;
  className?: string;
}

export function ProgressBarStep({
  currentStep,
  totalSteps,
  className,
}: ProgressBarStepProps) {
  return (
    <div className={cn("mb-8 flex gap-1.5", className)}>
      {Array.from({ length: totalSteps }, (_, i) => (
        <div
          key={i}
          className={cn(
            "h-1 flex-1 rounded-sm",
            i <= currentStep ? "bg-primary" : "bg-border",
          )}
        />
      ))}
    </div>
  );
}
