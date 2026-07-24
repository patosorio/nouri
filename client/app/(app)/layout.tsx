"use client";

import { AppShell } from "@/components/shared/AppShell";
import { RightPanelProvider } from "@/components/shared/right-panel-context";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RightPanelProvider>
      <AppShell>{children}</AppShell>
    </RightPanelProvider>
  );
}
