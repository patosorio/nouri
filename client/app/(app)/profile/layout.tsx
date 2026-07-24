"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageShell } from "@/components/shared/PageShell";
import { cn } from "@/lib/utils";

const SETTINGS_NAV = [
  { href: "/profile", label: "Profile", exact: true },
  { href: "/profile/diet", label: "Diet Preferences" },
  { href: "/profile/exclusions", label: "Exclusions" },
  { href: "/profile/notifications", label: "Notifications" },
  { href: "/profile/account", label: "Account" },
  { href: "/profile/billing", label: "Billing" },
] as const;

export default function ProfileLayout({
  children,
}: {
  children: ReactNode;
}) {
  const pathname = usePathname();

  return (
    <PageShell>
      <PageHeader eyebrow="Settings" title="Your Profile" />

      <div className="grid gap-10 lg:grid-cols-[220px_1fr]">
        <nav className="flex flex-col gap-0.5">
          {SETTINGS_NAV.map((item) => {
            const active = item.exact
              ? pathname === item.href
              : pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "border-l-2 px-4 py-3 font-mono text-[11px] uppercase tracking-[0.1em] no-underline",
                  active
                    ? "border-primary bg-primary/[0.06] text-primary"
                    : "border-transparent text-text-muted hover:text-text",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div>{children}</div>
      </div>
    </PageShell>
  );
}
