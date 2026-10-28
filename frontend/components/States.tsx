import Link from "next/link";

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="card p-8 text-center">
      <h2 className="font-display text-xl text-text">{title}</h2>
      {children && <div className="mt-2 text-muted text-sm max-w-xl mx-auto">{children}</div>}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: React.ReactNode }) {
  const cls = tone === "warn" ? "border-warn/40 bg-warn/8 text-warn" : "border-info/30 bg-info/8 text-info";
  return <div className={`rounded-lg border px-4 py-3 text-sm ${cls}`}>{children}</div>;
}

export function Pagination({ page, pageSize, total, href }: { page: number; pageSize: number; total: number; href: (p: number) => string }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-2 text-sm mt-4">
      <span className="text-muted">
        Page {page} of {pages} · {total} total
      </span>
      <div className="flex gap-2">
        {page > 1 ? (
          <Link className="px-3 py-1.5 rounded-md border border-line hover:bg-surface-2 focus-ring" href={href(page - 1)}>
            Previous
          </Link>
        ) : null}
        {page < pages ? (
          <Link className="px-3 py-1.5 rounded-md border border-line hover:bg-surface-2 focus-ring" href={href(page + 1)}>
            Next
          </Link>
        ) : null}
      </div>
    </nav>
  );
}

export function SectionTitle({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-2 mb-3">
      <h2 className="font-display text-xl text-text">{children}</h2>
      {aside}
    </div>
  );
}
