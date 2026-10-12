"use client";

import Link from "next/link";
import { History } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  GeneratePlanForm,
  type GeneratePlanDraft,
} from "@/components/plans/GeneratePlanForm";

interface GenerateDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  draft?: GeneratePlanDraft | null;
  conversationId?: string | null;
}

export function GenerateDrawer({
  open,
  onOpenChange,
  draft,
  conversationId,
}: GenerateDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-full gap-0 border-l border-border bg-bg p-0 shadow-[-16px_0_48px_rgba(30,53,87,0.25)] sm:max-w-[520px]"
      >
        <div className="flex items-center justify-between border-b border-border bg-surface px-7 py-6">
          <SheetTitle className="font-sans text-title font-semibold text-text">
            Generate <em>New Plan</em>
          </SheetTitle>
          <div className="flex items-center gap-2">
            <Link
              href="/chat"
              aria-label="Past conversations"
              title="Past conversations"
              className="flex size-10 items-center justify-center rounded-pill border-[1.5px] border-primary text-primary"
            >
              <History className="size-5" aria-hidden />
            </Link>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              aria-label="Close"
              className="border-0 bg-transparent text-[22px] leading-none text-text-muted"
            >
              ×
            </button>
          </div>
        </div>

        <div className="flex min-h-0 flex-1 flex-col px-7 py-[26px]">
          <GeneratePlanForm
            resetToken={open ? 1 : 0}
            draft={draft}
            conversationId={conversationId}
            onGenerated={() => onOpenChange(false)}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
