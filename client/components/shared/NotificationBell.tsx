"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Bell } from "lucide-react";
import { useMarkNotificationRead, useNotifications } from "@/hooks";
import { cn } from "@/lib/utils";

export function NotificationBell({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const { data } = useNotifications({ limit: 10 });
  const markRead = useMarkNotificationRead();

  const unread = useMemo(
    () => data?.data.filter((n) => !n.is_read) ?? [],
    [data],
  );

  return (
    <div className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
        className="relative flex size-9 items-center justify-center rounded-pill border border-border bg-surface text-text"
      >
        <Bell className="size-4" aria-hidden />
        {unread.length > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 min-w-[16px] rounded-pill bg-cta px-1 font-mono text-[9px] leading-[16px] text-white">
            {unread.length}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute bottom-12 left-0 z-20 w-[208px] rounded-card border border-border bg-surface p-2 shadow-lg">
          <p className="px-2 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
            Notifications
          </p>
          {data?.data.length ? (
            data.data.map((item) => {
              const planId =
                typeof item.data.plan_id === "string" ? item.data.plan_id : null;
              const href = planId ? `/plans/${planId}` : "/plans";
              return (
                <Link
                  key={item.id}
                  href={href}
                  onClick={() => {
                    if (!item.is_read) {
                      markRead.mutate(item.id);
                    }
                    setOpen(false);
                  }}
                  className={cn(
                    "block rounded-[10px] px-2.5 py-2 no-underline",
                    item.is_read ? "opacity-70" : "bg-primary/[0.06]",
                  )}
                >
                  <p className="m-0 font-sans text-body-sm font-medium text-text">
                    {item.title}
                  </p>
                  {item.body ? (
                    <p className="m-0 mt-0.5 font-sans text-[0.8rem] text-text-muted">
                      {item.body}
                    </p>
                  ) : null}
                </Link>
              );
            })
          ) : (
            <p className="px-2 py-3 font-sans text-body-sm italic text-text-muted">
              Nothing yet.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
