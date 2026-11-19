import type { Metadata } from "next";
import Link from "next/link";

import { RunList } from "@/components/RunList";
import { EmptyState, Notice, PageHeader, Pagination } from "@/components/States";
import { ApiError, api } from "@/lib/api";
import type { RunListResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Dungeon runs" };
export const dynamic = "force-dynamic";

const PAGE_SIZE = 25;

type Props = { searchParams: Promise<{ page?: string; dungeon?: string }> };

function Chip({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "focus-ring inline-flex h-7 items-center gap-1.5 rounded-full border px-3 text-sm whitespace-nowrap transition-colors",
        active ? "border-primary/40 bg-primary/10 text-primary" : "bg-card text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </Link>
  );
}

// Every run the home page counts, newest first, optionally one dungeon's.
export default async function RunsPage({ searchParams }: Props) {
  const sp = await searchParams;
  const page = Math.max(1, Number(sp.page ?? 1) || 1);
  const dungeon = sp.dungeon || undefined;
  let data: RunListResponse | null = null;
  let unknownDungeon = false;
  const [result, dungeons] = await Promise.all([
    api.runList({ page, pageSize: PAGE_SIZE, dungeon }).catch((e: unknown) => e),
    api.dungeons().catch(() => []),
  ]);
  if (result instanceof Error) unknownDungeon = result instanceof ApiError && result.status === 404;
  else data = result as RunListResponse;
  const title = data?.dungeon ? data.dungeon.name : "Dungeon runs";
  const query = (p: number) => `/runs?page=${p}${dungeon ? `&dungeon=${encodeURIComponent(dungeon)}` : ""}`;
  const withRuns = dungeons.filter((d) => d.runs > 0);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={title}
        description={data?.dungeon ? "Every recorded run of this dungeon, newest first." : "Every recorded dungeon run, newest first."}
      />
      {withRuns.length > 0 && (
        <nav aria-label="Dungeons" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 md:flex-wrap">
          <Chip href="/runs" active={!dungeon}>
            All dungeons
          </Chip>
          {withRuns.map((d) => (
            <Chip key={d.slug} href={`/runs?dungeon=${encodeURIComponent(d.slug)}`} active={dungeon === d.slug}>
              {d.name}
              <span className="text-xs text-faint tabular">{d.runs}</span>
            </Chip>
          ))}
        </nav>
      )}
      {unknownDungeon ? (
        <EmptyState title="Unknown dungeon">No dungeon matches this link.</EmptyState>
      ) : data === null ? (
        <Notice tone="warn">The run list is unavailable right now.</Notice>
      ) : data.total === 0 ? (
        <EmptyState title="No runs yet">Runs appear here once someone uploads one.</EmptyState>
      ) : (
        <div>
          <RunList runs={data.results} />
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} href={query} />
        </div>
      )}
    </div>
  );
}
