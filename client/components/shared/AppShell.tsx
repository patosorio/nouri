"use client";

import type { ReactNode } from "react";
import { SidebarNav } from "@/components/shared/SidebarNav";
import { useRightPanel } from "@/components/shared/right-panel-context";
import { cn } from "@/lib/utils";

interface AppShellProps {
  children: ReactNode;
  className?: string;
}

export function AppShell({ children, className }: AppShellProps) {
  const { rightPanel, rightPanelWidth } = useRightPanel();

  return (
    <div className={cn("relative z-[1] flex h-screen overflow-hidden", className)}>
      <aside className="h-full shrink-0">
        <SidebarNav />
      </aside>

      <main className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {children}
      </main>

      {rightPanel ? (
        <aside
          className="hidden h-full min-h-0 shrink-0 overflow-y-auto border-l border-border bg-surface px-[26px] py-7 lg:flex lg:flex-col"
          style={{ width: rightPanelWidth }}
        >
          {rightPanel}
        </aside>
      ) : null}
    </div>
  );
}
