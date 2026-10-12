"use client";

import { History } from "lucide-react";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { Skeleton } from "@/components/ui/skeleton";
import { useConversations } from "@/hooks";
import { cn } from "@/lib/utils";

interface ConversationHistoryPanelProps {
  activeId?: string | null;
  onSelect: (conversationId: string) => void;
  onNew: () => void;
  onBack: () => void;
  className?: string;
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function ConversationHistoryPanel({
  activeId,
  onSelect,
  onNew,
  onBack,
  className,
}: ConversationHistoryPanelProps) {
  const { data, isLoading, isError } = useConversations();

  return (
    <div className={cn("flex h-full flex-col gap-4", className)}>
      <div className="flex items-center justify-between gap-2">
        <EyebrowLabel>Past conversations</EyebrowLabel>
        <History className="size-4 text-primary" aria-hidden />
      </div>

      <button type="button" onClick={onNew} className="btn-primary w-full">
        New conversation
      </button>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto">
        {isLoading ? (
          <>
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </>
        ) : null}
        {isError ? (
          <p className="font-sans text-body-sm text-cta">
            Could not load conversations.
          </p>
        ) : null}
        {data && data.data.length === 0 ? (
          <p className="font-sans text-body-sm italic text-text-muted">
            No saved conversations yet.
          </p>
        ) : null}
        {data?.data.map((conversation) => (
          <button
            key={conversation.id}
            type="button"
            onClick={() => onSelect(conversation.id)}
            className={cn(
              "rounded-xl border bg-surface px-3.5 py-3 text-left",
              conversation.id === activeId
                ? "border-primary bg-primary/[0.06]"
                : "border-border",
            )}
          >
            <p className="m-0 font-sans text-body font-medium text-text">
              {formatWhen(conversation.updated_at)}
            </p>
            <p className="m-0 mt-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-text-muted">
              {conversation.message_count} messages
            </p>
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={onBack}
        className="border-0 bg-transparent font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted"
      >
        Back
      </button>
    </div>
  );
}
