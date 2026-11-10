"use client";

import { useState } from "react";

import { ClassName } from "@/components/Badges";
import { CharacterLink } from "@/components/CharacterLink";
import { MetricValue } from "@/components/MetricValue";
import { formatAmount, formatCount, formatDuration, formatRate, percent } from "@/lib/format";
import { METRIC_LABEL, roleLabel } from "@/lib/game";
import { isHidden, type DeathOut, type EncounterOut, type Participant } from "@/lib/types";

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

  const chip = (active: boolean) =>
    `rounded-full border px-3 py-1 text-sm focus-ring ${
      active ? "border-gold bg-gold/12 text-gold" : "border-line text-muted hover:text-text hover:border-line-strong"
    }`;

  return (
    <div className="flex flex-col gap-3">
      {encounters.length > 0 && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Show stats for">
          <button type="button" aria-pressed={selected === null} onClick={() => setSelected(null)} className={chip(selected === null)}>
            Whole run
          </button>
          {encounters.map((e, i) => (
            <button key={i} type="button" aria-pressed={selected === i} onClick={() => setSelected(i)} className={chip(selected === i)}>
              {labels[i]}
              {e.success === false && <span className="ml-1.5 text-bad">wipe</span>}
            </button>
          ))}
        </div>
      )}
      {fight && (
        <p className="text-sm text-muted">
          {fight.ended_at && (
            <>
              Fight length <span className="text-text tabular">{formatDuration((Date.parse(fight.ended_at) - Date.parse(fight.started_at)) / 1000)}</span>
              {" · "}
            </>
          )}
          {fight.success === true ? "Killed" : fight.success === false ? "Wipe" : "Outcome unknown"}
          {!hasData && " · No damage-meter data was recorded for this fight."}
          {hasData && fight.metrics_status === "partial" && " · The player recording this fight died during it, so these numbers stop there."}
        </p>
      )}
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-faint border-b border-line">
            <tr>
              <th className="px-4 py-3 font-medium">Character</th>
              <th className="px-3 py-3 font-medium">Role</th>
              {!fight && <th className="px-3 py-3 font-medium text-right">Presence</th>}
              {COLUMNS.map((c) => (
                <th key={c} className="px-3 py-3 font-medium text-right">
                  {METRIC_LABEL[c]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {participants.map((p, i) => (
              <tr key={i} className="border-b border-line/60 last:border-0 align-top">
                <td className="px-4 py-3 min-w-[12rem]">
                  <CharacterLink character={p.character} />
                  <div className="text-xs text-faint mt-0.5">
                    {!isHidden(p.character) && (
                      <>
                        Level {p.level ?? "?"} <ClassName classFile={p.class_file} />
                      </>
                    )}
                    {p.was_observer && <span className="ml-2 text-gold">· ForeverTracker user</span>}
                  </div>
                </td>
                <td className="px-3 py-3 text-muted">{roleLabel(p.role)}</td>
                {!fight && <td className="px-3 py-3 text-right tabular text-muted">{percent((p.presence_ratio ?? 0) * 100)}</td>}
                {COLUMNS.map((c) => (
                  <td key={c} className="px-3 py-3 text-right">
                    {fight ? (
                      (() => {
                        const v = isHidden(p.character) ? null : fightValue(fight, deaths, p.character.id, c);
                        return v === null ? <span className="text-faint">—</span> : <span className="tabular">{v}</span>;
                      })()
                    ) : (
                      <MetricValue metric={p.metrics[c]} />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
