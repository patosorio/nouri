"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";

interface ChatInputBarProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  value?: string;
  onChange?: (value: string) => void;
  className?: string;
}

export function ChatInputBar({
  onSend,
  disabled = false,
  value: controlledValue,
  onChange,
  className,
}: ChatInputBarProps) {
  const [internal, setInternal] = useState("");
  const value = controlledValue ?? internal;

  function setValue(next: string) {
    if (onChange) onChange(next);
    else setInternal(next);
  }

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        "flex items-center gap-3 rounded-pill border border-border bg-surface py-2.5 pl-5 pr-2.5",
        className,
      )}
    >
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Ask Nouri anything…"
        className="min-w-0 flex-1 border-0 bg-transparent font-sans text-body italic text-text outline-none placeholder:text-text-muted"
        aria-label="Chat message"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="shrink-0 rounded-pill bg-cta px-4 py-1.5 font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-white disabled:opacity-50"
      >
        Send
      </button>
    </form>
  );
}
