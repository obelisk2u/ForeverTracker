"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

export const NAV = [
  { href: "/runs", label: "Runs" },
  { href: "/characters", label: "Characters" },
  { href: "/download", label: "Download" },
  { href: "/about", label: "How it works" },
];

export function SiteNav({ className }: { className?: string }) {
  const pathname = usePathname() ?? "/";
  return (
    <>
      {NAV.map((n) => {
        const active = pathname === n.href || pathname.startsWith(`${n.href}/`);
        return (
          <Link
            key={n.href}
            href={n.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "focus-ring relative whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm transition-colors",
              active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
              className,
            )}
          >
            {n.label}
            {active && <span aria-hidden="true" className="absolute inset-x-2.5 -bottom-[13px] h-px bg-primary" />}
          </Link>
        );
      })}
    </>
  );
}
