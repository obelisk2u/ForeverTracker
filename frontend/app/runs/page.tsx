import type { Metadata } from "next";
import Link from "next/link";

import { RunList } from "@/components/RunList";
import { EmptyState, Notice, Pagination } from "@/components/States";
import { ApiError, api } from "@/lib/api";
import type { RunListResponse } from "@/lib/types";

export const metadata: Metadata = { title: "Dungeon runs" };
export const dynamic = "force-dynamic";

const PAGE_SIZE = 25;

type Props = { searchParams: Promise<{ page?: string; dungeon?: string }> };

// Every run the home page counts, newest first, optionally one dungeon's.
export default async function RunsPage({ searchParams }: Props) {
  const sp = await searchParams;
  const page = Math.max(1, Number(sp.page ?? 1) || 1);
  const dungeon = sp.dungeon || undefined;
  let data: RunListResponse | null = null;
  let unknownDungeon = false;
  try {
    data = await api.runList({ page, pageSize: PAGE_SIZE, dungeon });
  } catch (e) {
    unknownDungeon = e instanceof ApiError && e.status === 404;
  }
  const title = data?.dungeon ? data.dungeon.name : "Dungeon runs";
  const query = (p: number) => `/runs?page=${p}${dungeon ? `&dungeon=${encodeURIComponent(dungeon)}` : ""}`;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-3xl">{title}</h1>
        <p className="text-muted mt-2">
          {data?.dungeon ? "Every recorded run of this dungeon, newest first." : "Every recorded dungeon run, newest first."}
          {dungeon && (
            <>
              {" "}
              <Link href="/runs" className="underline">
                All dungeons
              </Link>
            </>
          )}
        </p>
      </div>
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
