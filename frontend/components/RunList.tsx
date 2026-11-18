import Link from "next/link";

import { OutcomeBadge } from "@/components/Badges";
import { formatShortDate } from "@/lib/format";
import type { ActivityItem } from "@/lib/types";

// One row per run, linking to its page: the home page's recent runs and the full run list.
export function RunList({ runs }: { runs: ActivityItem[] }) {
  return (
    <ul className="card divide-y divide-line/60">
      {runs.map((r) => (
        <li key={r.run_id}>
          <Link href={`/runs/${r.run_id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-surface-3/40 focus-ring">
            <div className="min-w-0">
              <div className="text-text truncate">{r.dungeon.name}</div>
              <div className="text-xs text-faint">
                {formatShortDate(r.started_at)} · {r.participants} players · {r.observers} observer{r.observers === 1 ? "" : "s"}
              </div>
            </div>
            <OutcomeBadge outcome={r.outcome} confidence={r.completion_confidence} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
