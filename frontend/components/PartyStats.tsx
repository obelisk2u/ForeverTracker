"use client";

import { Eye } from "lucide-react";
import { useState } from "react";

import { ClassName, RoleIcon } from "@/components/Badges";
import { CharacterLink } from "@/components/CharacterLink";
import { MetricValue } from "@/components/MetricValue";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatAmount, formatCount, formatDuration, formatRate } from "@/lib/format";
import { METRIC_LABEL, classColor } from "@/lib/game";
import { isHidden, type DeathOut, type EncounterOut, type Participant } from "@/lib/types";
import { cn } from "@/lib/utils";

const COLUMNS = ["damage_done", "dps", "healing_done", "hps", "interrupts", "dispels", "deaths"] as const;
type Column = (typeof COLUMNS)[number];

// One boss attempt's value for a character: totals from that fight's damage meter, rates over its
// combat time, and deaths between the pull and the end of the fight.
function fightValue(e: EncounterOut, deaths: DeathOut[], characterId: string, column: Column): string | null {
  const m = e.metrics?.[characterId];
  if (column === "deaths") {
    const start = Date.parse(e.started_at);
    const end = e.ended_at ? Date.parse(e.ended_at) : Infinity;
    return formatCount(
      deaths.filter((d) => d.character_id === characterId && Date.parse(d.occurred_at) >= start && Date.parse(d.occurred_at) <= end).length,
    );
  }
  if (!m) return null;
  const seconds = e.combat_seconds ?? 0;
  if (column === "dps" || column === "hps") {
    const total = m[column === "dps" ? "damage_done" : "healing_done"];
    return total !== undefined && seconds > 0 ? formatRate(total / seconds) : null;
  }
  const v = m[column];
  if (v === undefined) return null;
  return column === "interrupts" || column === "dispels" ? formatCount(v) : formatAmount(v);
}

function attemptLabels(encounters: EncounterOut[]): string[] {
  const seen = new Map<number, number>();
  const totals = new Map<number, number>();
  for (const e of encounters) totals.set(e.encounter_id, (totals.get(e.encounter_id) ?? 0) + 1);
  return encounters.map((e) => {
    const n = (seen.get(e.encounter_id) ?? 0) + 1;
    seen.set(e.encounter_id, n);
    const name = e.name ?? `Encounter ${e.encounter_id}`;
    return (totals.get(e.encounter_id) ?? 1) > 1 ? `${name} #${n}` : name;
  });
}

type MeterRow = { name: string; classFile: string | null; total: number; rate: number | null };

// A total and its per-second rate for the whole run (the reconciled metrics) or for one fight.
function meterRows(participants: Participant[], fight: EncounterOut | null, kind: "damage" | "healing"): MeterRow[] {
  const totalKey = kind === "damage" ? "damage_done" : "healing_done";
  const rateKey = kind === "damage" ? "dps" : "hps";
  const rows: MeterRow[] = [];
  for (const p of participants) {
    const name = isHidden(p.character) ? "Hidden character" : p.character.full_name;
    let total: number | null = null;
    let rate: number | null = null;
    if (fight) {
      const m = isHidden(p.character) ? undefined : fight.metrics?.[p.character.id];
      total = m?.[totalKey] ?? null;
      const seconds = fight.combat_seconds ?? 0;
      rate = total !== null && seconds > 0 ? total / seconds : null;
    } else {
      const t = p.metrics[totalKey];
      const r = p.metrics[rateKey];
      total = t && t.status !== "unavailable" ? (t.value ?? null) : null;
      rate = r && r.status !== "unavailable" ? (r.value ?? null) : null;
    }
    if (total !== null && total > 0) rows.push({ name, classFile: p.class_file, total, rate });
  }
  return rows.sort((a, b) => b.total - a.total);
}

// Like the meter in the game: one bar per player, longest first, in their class colour.
function Meter({ title, unit, rows }: { title: string; unit: string; rows: MeterRow[] }) {
  if (rows.length === 0) return null;
  const top = rows[0].total;
  const sum = rows.reduce((s, r) => s + r.total, 0);
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="mb-3 flex items-baseline justify-between text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{title}</span>
        <span className="tabular">{formatAmount(sum)} total</span>
      </div>
      <ol className="flex flex-col gap-2.5">
        {rows.map((r, i) => (
          <li key={i}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="truncate text-foreground">{r.name}</span>
              <span className="shrink-0 text-foreground tabular">
                {formatAmount(r.total)}
                {r.rate !== null && (
                  <span className="ml-1.5 text-xs text-faint">
                    {formatRate(r.rate)} {unit}
                  </span>
                )}
                <span className="ml-1.5 inline-block w-9 text-right text-xs text-faint">{Math.round((r.total / sum) * 100)}%</span>
              </span>
            </div>
            <div aria-hidden="true" className="mt-1 h-1.5 rounded-full bg-muted">
              <div className="h-1.5 rounded-full" style={{ width: `${(r.total / top) * 100}%`, backgroundColor: classColor(r.classFile) }} />
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function PartyStats({
  participants,
  encounters,
  deaths,
}: {
  participants: Participant[];
  encounters: EncounterOut[];
  deaths: DeathOut[];
}) {
  // null: the whole run; otherwise the index of a boss attempt.
  const [selected, setSelected] = useState<number | null>(null);
  const fight = selected === null ? null : encounters[selected];
  const labels = attemptLabels(encounters);
  const hasData = fight !== null && Object.keys(fight.metrics ?? {}).length > 0;
  const damage = meterRows(participants, fight, "damage");
  const healing = meterRows(participants, fight, "healing");

  const segment = (active: boolean) =>
    cn(
      "focus-ring inline-flex h-7 items-center gap-2 rounded-md px-3 text-sm whitespace-nowrap transition-colors",
      active ? "bg-accent text-foreground shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground",
    );

  return (
    <div className="flex flex-col gap-4">
      {encounters.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="inline-flex max-w-full flex-wrap gap-1 rounded-lg border bg-card p-1" role="group" aria-label="Show stats for">
            <button type="button" aria-pressed={selected === null} onClick={() => setSelected(null)} className={segment(selected === null)}>
              Whole run
            </button>
            {encounters.map((e, i) => (
              <button key={i} type="button" aria-pressed={selected === i} onClick={() => setSelected(i)} className={segment(selected === i)}>
                <span
                  aria-hidden="true"
                  className={cn(
                    "size-1.5 rotate-45 rounded-[1px] border",
                    e.success === true ? "border-primary bg-primary" : e.success === false ? "border-destructive" : "border-faint",
                  )}
                />
                {labels[i]}
                {e.success === false && <span className="text-destructive">wipe</span>}
              </button>
            ))}
          </div>
          {fight && (
            <p className="text-sm text-muted-foreground">
              {fight.ended_at && (
                <>
                  Fight length <span className="text-foreground tabular">{formatDuration((Date.parse(fight.ended_at) - Date.parse(fight.started_at)) / 1000)}</span>
                  {" · "}
                </>
              )}
              {fight.success === true ? "Killed" : fight.success === false ? "Wipe" : "Outcome unknown"}
              {!hasData && " · No damage-meter data was recorded for this fight."}
              {hasData && fight.metrics_status === "partial" && " · The player recording this fight died during it, so these numbers stop there."}
            </p>
          )}
        </div>
      )}

      {(damage.length > 0 || healing.length > 0) && (
        <div className="grid gap-4 md:grid-cols-2">
          <Meter title="Damage" unit="dps" rows={damage} />
          <Meter title="Healing" unit="hps" rows={healing} />
        </div>
      )}

      <div className="overflow-hidden rounded-xl border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="h-9 px-4 text-xs font-medium text-muted-foreground">Character</TableHead>
              {COLUMNS.map((c) => (
                <TableHead key={c} className="h-9 px-3 text-right text-xs font-medium text-muted-foreground">
                  {METRIC_LABEL[c]}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {participants.map((p, i) => (
              <TableRow key={i}>
                <TableCell className="min-w-[13rem] px-4 py-2.5">
                  <div className="flex items-center gap-2.5">
                    <RoleIcon role={p.role} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <CharacterLink character={p.character} showDot={false} />
                        {p.was_observer && (
                          <span title="Recorded this run with ForeverTracker">
                            <Eye aria-label="ForeverTracker user" className="size-3.5 text-primary" />
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-faint">
                        {!isHidden(p.character) && (
                          <>
                            Level {p.level ?? "?"} <ClassName classFile={p.class_file} />
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </TableCell>
                {COLUMNS.map((c) => (
                  <TableCell key={c} className="px-3 py-2.5 text-right text-foreground tabular">
                    {fight ? (
                      (() => {
                        const v = isHidden(p.character) ? null : fightValue(fight, deaths, p.character.id, c);
                        return v === null ? <span className="text-faint">—</span> : <span className="tabular">{v}</span>;
                      })()
                    ) : (
                      <MetricValue metric={p.metrics[c]} />
                    )}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
