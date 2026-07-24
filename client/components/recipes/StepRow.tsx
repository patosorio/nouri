import { cn } from "@/lib/utils";

interface StepRowProps {
  stepNumber: number;
  instruction: string;
  durationMinutes?: number | null;
  tips?: string | null;
  className?: string;
}

export function StepRow({
  stepNumber,
  instruction,
  durationMinutes,
  tips,
  className,
}: StepRowProps) {
  return (
    <li
      className={cn(
        "flex gap-[18px] border-b border-primary/10 py-4 last:border-0",
        className,
      )}
    >
      <span className="min-w-8 shrink-0 font-mono text-title text-neutral">
        {stepNumber}
      </span>
      <div>
        <p className="m-0 font-sans text-body text-text">{instruction}</p>
        {durationMinutes != null ? (
          <p className="mt-1 font-mono text-label uppercase text-text-muted">
            {durationMinutes} min
          </p>
        ) : null}
        {tips ? (
          <p className="mt-1 font-sans text-body-sm italic text-text-muted">
            Tip: {tips}
          </p>
        ) : null}
      </div>
    </li>
  );
}
