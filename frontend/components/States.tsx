import { ChevronLeft, ChevronRight, Info, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed px-6 py-12 text-center">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      {children && <div className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: React.ReactNode }) {
  const Icon = tone === "warn" ? TriangleAlert : Info;
  return (
    <div
      className={cn(
        "flex gap-3 rounded-lg border px-4 py-3 text-sm",
        tone === "warn" ? "border-warning/25 bg-warning/5 text-warning" : "border-info/25 bg-info/5 text-info",
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function Pagination({ page, pageSize, total, href }: { page: number; pageSize: number; total: number; href: (p: number) => string }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="mt-4 flex items-center justify-between gap-2 text-sm">
      <span className="text-muted-foreground">
        Page <span className="text-foreground tabular">{page}</span> of {pages} · {total} total
      </span>
      <div className="flex gap-2">
        {page > 1 ? (
          <Link className={buttonVariants({ variant: "outline", size: "sm" })} href={href(page - 1)}>
            <ChevronLeft aria-hidden="true" />
            Previous
          </Link>
        ) : null}
        {page < pages ? (
          <Link className={buttonVariants({ variant: "outline", size: "sm" })} href={href(page + 1)}>
            Next
            <ChevronRight aria-hidden="true" />
          </Link>
        ) : null}
      </div>
    </nav>
  );
}

export function SectionTitle({ children, aside, id }: { children: React.ReactNode; aside?: React.ReactNode; id?: string }) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <h2 id={id} className="text-sm font-semibold text-foreground">
        {children}
      </h2>
      {aside && <div className="text-xs text-muted-foreground">{aside}</div>}
    </div>
  );
}

// The title block every page starts with.
export function PageHeader({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  eyebrow?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b pb-6">
      <div className="min-w-0">
        {eyebrow && <div className="mb-2 text-sm text-muted-foreground">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-muted-foreground">{description}</p>}
      </div>
      {actions}
    </div>
  );
}
