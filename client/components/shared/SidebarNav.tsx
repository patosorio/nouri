"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NotificationBell } from "@/components/shared/NotificationBell";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
}

const PRIMARY_NAV: NavItem[] = [
  { href: "/chat", label: "Chat" },
  { href: "/plans", label: "Meal Planner" },
  { href: "/recipes", label: "Recipes" },
  { href: "/calendar", label: "Calendar" },
  { href: "/shopping-list", label: "Shopping List" },
  { href: "/pantry", label: "Pantry" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/chat") return pathname === "/chat" || pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

const navItemClass =
  "block rounded-lg px-3 py-2.5 font-mono text-[10px] font-normal uppercase leading-none tracking-[0.12em] no-underline transition-colors";

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="flex h-full w-sidebar flex-col border-r border-border bg-surface px-4 py-6">
      <Link
        href="/chat"
        className="mb-6 px-3 font-sans text-nav-logo font-medium leading-none text-text"
      >
        nouri
      </Link>

      <div className="flex flex-col gap-0.5">
        {PRIMARY_NAV.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                navItemClass,
                active
                  ? "bg-primary/10 text-primary"
                  : "text-text-muted hover:bg-primary/[0.04] hover:text-text",
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </div>

      <div className="mt-auto flex flex-col gap-3">
        <NotificationBell />
        <div className="mx-1 h-px bg-border" />
        <Link
          href="/profile"
          className={cn(
            navItemClass,
            "text-center",
            isActive(pathname, "/profile")
              ? "bg-primary/10 text-primary"
              : "text-text-muted hover:bg-primary/[0.04] hover:text-text",
          )}
        >
          Profile / Settings
        </Link>
      </div>
    </nav>
  );
}
