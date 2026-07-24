import Link from "next/link";
import type { ReactNode } from "react";
import { RawCookedTag } from "@/components/shared/RawCookedTag";
import { cn } from "@/lib/utils";

interface AuthSplitShellProps {
  children: ReactNode;
  editorialTitle: ReactNode;
  editorialSubtitle: string;
  tagType: "raw" | "cooked";
  className?: string;
}

export function AuthSplitShell({
  children,
  editorialTitle,
  editorialSubtitle,
  tagType,
  className,
}: AuthSplitShellProps) {
  return (
    <div className={cn("relative z-[1] flex min-h-screen", className)}>
      <div className="flex w-full max-w-[560px] flex-col justify-center bg-surface px-10 py-16 sm:px-16 lg:px-20">
        <Link
          href="/"
          className="mb-12 font-sans text-nav-logo font-semibold text-text"
        >
          nouri
        </Link>
        {children}
      </div>

      <div className="relative hidden flex-1 flex-col justify-center overflow-hidden bg-primary-dark px-12 py-16 lg:flex lg:px-20">
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_80%_15%,rgba(243,231,81,0.14),transparent_55%)]"
          aria-hidden
        />
        <h1 className="relative z-[1] max-w-lg font-sans text-display font-medium leading-[1.1] text-white [&_em]:text-highlight">
          {editorialTitle}
        </h1>
        <p className="relative z-[1] mt-5 max-w-[420px] font-sans text-[1.1rem] italic leading-relaxed text-white/70">
          {editorialSubtitle}
        </p>
        <div className="relative z-[1] mt-9">
          <RawCookedTag
            type={tagType}
            className="border border-white/15 bg-white/10 text-white/60 [&_span]:bg-highlight"
          />
        </div>
      </div>
    </div>
  );
}
