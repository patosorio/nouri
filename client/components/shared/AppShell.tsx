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
    <div className={cn("relative z-[1] flex min-h-screen", className)}>
      <aside className="sticky top-0 h-screen shrink-0">
        <SidebarNav />
      </aside>

      <main className="flex min-h-screen min-w-0 flex-1 flex-col overflow-hidden">
        {children}
      </main>

      {rightPanel ? (
        <aside
          className="sticky top-0 hidden h-screen shrink-0 overflow-y-auto border-l border-border bg-surface px-[26px] py-7 lg:flex lg:flex-col"
          style={{ width: rightPanelWidth }}
        >
          {rightPanel}
        </aside>
      ) : null}
    </div>
  );
}
