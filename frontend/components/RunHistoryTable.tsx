import Link from "next/link";

import { ClassDot, OutcomeBadge, RoleIcon } from "@/components/Badges";
import { LocalTime } from "@/components/LocalTime";
import { MetricValue } from "@/components/MetricValue";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDuration } from "@/lib/format";
import { classColor, roleLabel } from "@/lib/game";
import { isHidden, type RunRow } from "@/lib/types";

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

const HEAD = "h-9 px-3 text-xs font-medium text-muted-foreground";

// Desktop: a table. Mobile: a card per run. Both render the same data.
export function RunHistoryTable({ rows, characterId }: { rows: RunRow[]; characterId: string }) {
  return (
    <div>
      <div className="hidden md:block overflow-hidden rounded-xl border bg-card" data-testid="history-table">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className={`${HEAD} pl-4`}>Dungeon</TableHead>
              <TableHead className={HEAD}>Date</TableHead>
              <TableHead className={HEAD}>Duration</TableHead>
              <TableHead className={HEAD}>Party</TableHead>
              <TableHead className={`${HEAD} text-right`}>Output</TableHead>
              <TableHead className={`${HEAD} text-right`}>Deaths</TableHead>
              <TableHead className={`${HEAD} text-right`}>Interrupts</TableHead>
              <TableHead className={`${HEAD} pr-4`}>Outcome</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.run_id}>
                <TableCell className="py-2.5 pl-4">
                  <div className="flex items-center gap-2.5">
                    <RoleIcon role={row.role} />
                    <div>
                      <Link href={`/runs/${row.run_id}`} className="focus-ring rounded-sm font-medium text-foreground hover:text-primary">
                        {row.dungeon.name}
                      </Link>
                      {row.observers > 1 && <div className="text-xs text-faint">{row.observers} observers</div>}
                    </div>
                  </div>
                </TableCell>
                <TableCell className="px-3 text-muted-foreground">
                  <LocalTime iso={row.started_at} format="short" />
                </TableCell>
                <TableCell className="px-3 text-muted-foreground tabular">{formatDuration(row.duration_seconds)}</TableCell>
                <TableCell className="px-3 whitespace-normal">
                  <ul className="flex max-w-[17rem] flex-wrap gap-x-2.5 gap-y-0.5" aria-label="Party">
                    {row.party
                      .filter((p) => !("id" in p.character) || p.character.id !== characterId)
                      .map((p, i) => (
                        <li key={i} className="inline-flex items-center gap-1 text-xs">
                          {isHidden(p.character) ? (
                            <span className="text-faint italic">Hidden</span>
                          ) : (
                            <Link
                              href={`/character/${p.character.namespace}/${p.character.id}`}
                              title={p.character.full_name}
                              className="focus-ring inline-flex items-center gap-1 rounded-sm hover:underline"
                              style={{ color: classColor(p.character.class_file) }}
                            >
                              <ClassDot classFile={p.character.class_file} className="size-1.5" />
                              {p.character.name}
                            </Link>
                          )}
                        </li>
                      ))}
                  </ul>
                </TableCell>
                <TableCell className="px-3 text-right text-foreground tabular">
                  <PerformanceCell row={row} />
                </TableCell>
                <TableCell className="px-3 text-right text-foreground tabular">
                  <MetricValue metric={row.metrics.deaths} />
                </TableCell>
                <TableCell className="px-3 text-right text-foreground tabular">
                  <MetricValue metric={row.metrics.interrupts} />
                </TableCell>
                <TableCell className="pr-4">
                  <OutcomeBadge outcome={row.outcome} confidence={row.completion_confidence} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ul className="md:hidden flex flex-col divide-y overflow-hidden rounded-xl border bg-card" data-testid="history-cards">
        {rows.map((row) => (
          <li key={row.run_id} className="p-4">
            <div className="flex items-start justify-between gap-2">
              <Link href={`/runs/${row.run_id}`} className="font-medium text-foreground hover:text-primary">
                {row.dungeon.name}
              </Link>
              <OutcomeBadge outcome={row.outcome} confidence={row.completion_confidence} />
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
              <LocalTime iso={row.started_at} format="short" />
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
