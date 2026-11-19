import { ChevronRight, Eye, Users } from "lucide-react";
import Link from "next/link";

import { OutcomeBadge } from "@/components/Badges";
import { LocalTime } from "@/components/LocalTime";
import type { ActivityItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const COLUMNS = "md:grid-cols-[minmax(0,1fr)_3.5rem_4.5rem_5.5rem_7.5rem_1rem]";

// One row per run, linking to its page: the home page's recent runs and the full run list.
export function RunList({ runs, now }: { runs: ActivityItem[]; now?: Date }) {
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div
        aria-hidden="true"
        className={cn("hidden items-center gap-4 border-b px-4 py-2.5 text-xs font-medium text-muted-foreground md:grid", COLUMNS)}
      >
        <span>Dungeon</span>
        <span>Players</span>
        <span>Observers</span>
        <span>Started</span>
        <span>Outcome</span>
        <span />
      </div>
      <ul className="divide-y">
        {runs.map((r) => (
          <li key={r.run_id}>
            <Link
              href={`/runs/${r.run_id}`}
              className={cn(
                "group focus-ring grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3 transition-colors hover:bg-accent/60",
                COLUMNS,
              )}
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">{r.dungeon.name}</span>
                <span className="block text-xs text-faint md:hidden">
                  <LocalTime iso={r.started_at} format="short" /> · {r.participants} players · {r.observers} observer{r.observers === 1 ? "" : "s"}
                </span>
              </span>
              <span className="hidden items-center gap-1.5 text-sm text-muted-foreground tabular md:inline-flex">
                <Users aria-hidden="true" className="size-3.5 text-faint" />
                {r.participants}
              </span>
              <span className="hidden items-center gap-1.5 text-sm text-muted-foreground tabular md:inline-flex">
                <Eye aria-hidden="true" className="size-3.5 text-faint" />
                {r.observers}
              </span>
              <LocalTime
                iso={r.started_at}
                format="relative"
                now={now}
                className="hidden text-sm whitespace-nowrap text-muted-foreground md:block"
              />
              <span className="justify-self-end md:justify-self-start">
                <OutcomeBadge outcome={r.outcome} confidence={r.completion_confidence} />
              </span>
              <ChevronRight
                aria-hidden="true"
                className="hidden size-4 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-foreground md:block"
              />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
