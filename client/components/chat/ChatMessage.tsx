import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string | ReactNode;
  className?: string;
}

const markdownComponents = {
  p: ({ children }: { children?: ReactNode }) => (
    <p className="m-0 [&:not(:last-child)]:mb-3">{children}</p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="my-0 list-disc space-y-1.5 pl-5">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="my-0 list-decimal space-y-1.5 pl-5">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li className="m-0 leading-[1.55]">{children}</li>
  ),
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-medium">{children}</strong>
  ),
};

export function ChatMessage({ role, content, className }: ChatMessageProps) {
  const isUser = role === "user";

  return (
    <div
      className={cn(
        "flex w-full",
        isUser ? "justify-end" : "justify-start",
        className,
      )}
    >
      <div className="flex max-w-[560px] flex-col gap-2">
        {!isUser ? (
          <span className="font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-primary">
            Nouri
          </span>
        ) : null}
        <div
          className={cn(
            "px-4 py-3 font-sans text-body leading-[1.5]",
            isUser
              ? "rounded-[16px_16px_4px_16px] bg-primary text-white"
              : "rounded-[16px_16px_16px_4px] border border-border bg-surface text-text",
          )}
        >
          {typeof content !== "string" ? (
            content
          ) : isUser ? (
            <p className="m-0">{content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {content}
            </ReactMarkdown>
          )}
        </div>
      </div>
    </div>
  );
}
