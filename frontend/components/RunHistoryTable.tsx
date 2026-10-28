import Link from "next/link";

import { OutcomeBadge } from "@/components/Badges";
import { CharacterLink } from "@/components/CharacterLink";
import { MetricValue } from "@/components/MetricValue";
import { formatDuration, formatShortDate } from "@/lib/format";
import { roleLabel } from "@/lib/game";
import type { RunRow } from "@/lib/types";

function PerformanceCell({ row }: { row: RunRow }) {
  const healer = row.role === "HEALER";
  const metric = healer ? row.metrics.hps : row.metrics.dps;
  return (
    <span className="inline-flex items-baseline gap-1">
      <MetricValue metric={metric} />
      <span className="text-xs text-faint">{healer ? "HPS" : "DPS"}</span>
    </span>
  );
}

// Desktop: a table. Mobile: a card per run. Both render the same data.
export function RunHistoryTable({ rows, characterId }: { rows: RunRow[]; characterId: string }) {
  return (
    <div>
      <div className="hidden md:block overflow-x-auto card" data-testid="history-table">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-faint border-b border-line">
            <tr>
              <th className="px-4 py-3 font-medium">Dungeon</th>
              <th className="px-3 py-3 font-medium">Date</th>
              <th className="px-3 py-3 font-medium">Duration</th>
              <th className="px-3 py-3 font-medium">Role</th>
              <th className="px-3 py-3 font-medium">Party</th>
              <th className="px-3 py-3 font-medium text-right">Output</th>
              <th className="px-3 py-3 font-medium text-right">Deaths</th>
              <th className="px-3 py-3 font-medium text-right">Interrupts</th>
              <th className="px-4 py-3 font-medium">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.run_id} className="border-b border-line/60 last:border-0 hover:bg-surface-3/40">
                <td className="px-4 py-3">
                  <Link href={`/runs/${row.run_id}`} className="font-medium text-gold hover:underline focus-ring rounded-sm">
                    {row.dungeon.name}
                  </Link>
                  {row.observers > 1 && <div className="text-xs text-faint">{row.observers} observers</div>}
                </td>
                <td className="px-3 py-3 whitespace-nowrap text-muted">
                  <time dateTime={row.started_at}>{formatShortDate(row.started_at)}</time>
                </td>
                <td className="px-3 py-3 tabular text-muted">{formatDuration(row.duration_seconds)}</td>
                <td className="px-3 py-3 text-muted">{roleLabel(row.role)}</td>
                <td className="px-3 py-3">
                  <ul className="flex flex-col gap-0.5 max-w-[14rem]" aria-label="Party">
                    {row.party
                      .filter((p) => !("id" in p.character) || p.character.id !== characterId)
                      .map((p, i) => (
                        <li key={i} className="text-xs truncate">
                          <CharacterLink character={p.character} />
                        </li>
                      ))}
                  </ul>
                </td>
                <td className="px-3 py-3 text-right">
                  <PerformanceCell row={row} />
                </td>
                <td className="px-3 py-3 text-right">
                  <MetricValue metric={row.metrics.deaths} />
                </td>
                <td className="px-3 py-3 text-right">
                  <MetricValue metric={row.metrics.interrupts} />
                </td>
                <td className="px-4 py-3">
                  <OutcomeBadge outcome={row.outcome} confidence={row.completion_confidence} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="md:hidden flex flex-col gap-3" data-testid="history-cards">
        {rows.map((row) => (
          <li key={row.run_id} className="card p-4">
            <div className="flex items-start justify-between gap-2">
              <Link href={`/runs/${row.run_id}`} className="font-medium text-gold hover:underline">
                {row.dungeon.name}
              </Link>
              <OutcomeBadge outcome={row.outcome} confidence={row.completion_confidence} />
            </div>
            <div className="mt-1 text-xs text-muted flex flex-wrap gap-x-3">
              <time dateTime={row.started_at}>{formatShortDate(row.started_at)}</time>
              <span>{formatDuration(row.duration_seconds)}</span>
              <span>{roleLabel(row.role)}</span>
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
              <div>
                <dt className="text-xs text-faint">{row.role === "HEALER" ? "HPS" : "DPS"}</dt>
                <dd>
                  <MetricValue metric={row.role === "HEALER" ? row.metrics.hps : row.metrics.dps} />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-faint">Deaths</dt>
                <dd>
                  <MetricValue metric={row.metrics.deaths} />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-faint">Interrupts</dt>
                <dd>
                  <MetricValue metric={row.metrics.interrupts} />
                </dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </div>
  );
}
