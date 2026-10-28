import { Badge, ClassName, OutcomeBadge } from "@/components/Badges";
import { CharacterLink } from "@/components/CharacterLink";
import { Timestamp } from "@/components/Freshness";
import { MetricLegend, MetricValue } from "@/components/MetricValue";
import { Notice, SectionTitle } from "@/components/States";
import { formatDuration, formatNumber, percent } from "@/lib/format";
import { METRIC_LABEL, RESOLUTION_LABEL, SOURCE_LABEL, namespaceLabel, roleLabel } from "@/lib/game";
import { isHidden, type Participant, type RunDetail } from "@/lib/types";

const COLUMNS = ["damage_done", "dps", "healing_done", "hps", "interrupts", "dispels", "deaths"] as const;

function Provenance({ p }: { p: Participant }) {
  const entries = Object.entries(p.candidates);
  if (entries.length === 0) return null;
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer text-faint hover:text-muted">Sources and candidate values</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full">
          <thead className="text-faint text-left">
            <tr>
              <th className="py-1 pr-3 font-medium">Metric</th>
              <th className="py-1 pr-3 font-medium">Observer</th>
              <th className="py-1 pr-3 font-medium">Source</th>
              <th className="py-1 pr-3 font-medium text-right">Value</th>
              <th className="py-1 pr-3 font-medium">Coverage</th>
            </tr>
          </thead>
          <tbody>
            {entries.flatMap(([metric, cands]) =>
              cands.map((c, i) => (
                <tr key={`${metric}-${i}`} className="border-t border-line/40">
                  <td className="py-1 pr-3">{METRIC_LABEL[metric] ?? metric}</td>
                  <td className="py-1 pr-3">{c.observer}</td>
                  <td className="py-1 pr-3 text-muted">{SOURCE_LABEL[c.source] ?? c.source}</td>
                  <td className="py-1 pr-3 text-right tabular">
                    {c.value === null || c.value === undefined ? "—" : formatNumber(c.value, metric === "deaths" || metric === "interrupts" || metric === "dispels" ? "count" : "amount")}
                  </td>
                  <td className="py-1 pr-3 text-muted">
                    {c.coverage.replace("_", " ")} {c.coverage_ratio !== null && c.coverage_ratio !== undefined ? `(${percent(c.coverage_ratio * 100)})` : ""}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
        {Object.entries(p.conflicts).map(([metric, conflict]) => (
          <p key={metric} className="mt-2 text-bad">
            {METRIC_LABEL[metric] ?? metric}: {(conflict as { reason?: string }).reason === "sources_disagree" ? "sources disagree" : "observers disagree"}; the
            best-covered value is shown.
          </p>
        ))}
      </div>
    </details>
  );
}

export function RunDetailView({ run }: { run: RunDetail }) {
  const deathCoverage = String(run.coverage.deaths ?? "none");
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-display text-3xl text-gold">{run.dungeon.name}</h1>
          <OutcomeBadge outcome={run.outcome} confidence={run.completion_confidence} />
          {run.match_status === "reconciled" && (
            <Badge tone="good" title="Several ForeverTracker users recorded this run; their records were merged">
              Reconciled from {run.contributor_count} observers
            </Badge>
          )}
          {run.match_status === "unresolved" && (
            <Badge tone="warn" title="This record might belong to another run; kept separate pending review">
              Unresolved match
            </Badge>
          )}
        </div>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted">
          <div>
            <dt className="inline text-faint">Started </dt>
            <dd className="inline text-text">
              <Timestamp iso={run.started_at} />
            </dd>
          </div>
          <div>
            <dt className="inline text-faint">Duration </dt>
            <dd className="inline text-text tabular">{run.ended_at ? formatDuration(run.duration_seconds) : "still in progress"}</dd>
          </div>
          <div>
            <dt className="inline text-faint">Difficulty </dt>
            <dd className="inline text-text">{run.difficulty_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="inline text-faint">Namespace </dt>
            <dd className="inline text-text">{namespaceLabel(run.namespace.slug)}</dd>
          </div>
          <div>
            <dt className="inline text-faint">Last updated </dt>
            <dd className="inline text-text">
              <Timestamp iso={run.last_observed_at} />
            </dd>
          </div>
        </dl>
        {run.is_synthetic && <Notice tone="warn">Synthetic development run generated by the simulator.</Notice>}
        {run.outcome !== "completed" && (
          <p className="text-sm text-muted">
            {run.outcome === "left" || run.outcome === "disconnected"
              ? "The observers left before any completion event. That does not mean the group failed; ForeverTracker never infers a completion from leaving an instance."
              : run.outcome === "unknown"
                ? "No completion event was recorded, so the outcome is unknown."
                : null}
          </p>
        )}
      </header>

      <section>
        <SectionTitle aside={<MetricLegend />}>Party</SectionTitle>
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-faint border-b border-line">
              <tr>
                <th className="px-4 py-3 font-medium">Character</th>
                <th className="px-3 py-3 font-medium">Role</th>
                <th className="px-3 py-3 font-medium text-right">Presence</th>
                {COLUMNS.map((c) => (
                  <th key={c} className="px-3 py-3 font-medium text-right">
                    {METRIC_LABEL[c]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {run.participants.map((p, i) => (
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
                      {p.observed_by > 1 && <span className="ml-2">· seen by {p.observed_by}</span>}
                    </div>
                    {!isHidden(p.character) && <Provenance p={p} />}
                  </td>
                  <td className="px-3 py-3 text-muted">{roleLabel(p.role)}</td>
                  <td className="px-3 py-3 text-right tabular text-muted">{percent((p.presence_ratio ?? 0) * 100)}</td>
                  {COLUMNS.map((c) => (
                    <td key={c} className="px-3 py-3 text-right">
                      <MetricValue metric={p.metrics[c]} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {Number(run.coverage.roster_entries_unidentified ?? 0) > 0 && (
          <p className="mt-2 text-xs text-faint">
            {String(run.coverage.roster_entries_unidentified)} roster entr{Number(run.coverage.roster_entries_unidentified) === 1 ? "y" : "ies"} could not be identified
            safely (secret or ambiguous identity) and {Number(run.coverage.roster_entries_unidentified) === 1 ? "is" : "are"} not shown.
          </p>
        )}
      </section>

      <div className="grid lg:grid-cols-2 gap-6">
        <section>
          <SectionTitle>Boss encounters</SectionTitle>
          {run.encounters.length === 0 ? (
            <p className="text-sm text-muted">No boss encounters were recorded.</p>
          ) : (
            <ol className="card divide-y divide-line/60">
              {run.encounters.map((e, i) => (
                <li key={i} className="px-4 py-3 flex items-center justify-between gap-3 text-sm">
                  <div>
                    <div className="text-text">{e.name ?? `Encounter ${e.encounter_id}`}</div>
                    <div className="text-xs text-faint">
                      <Timestamp iso={e.started_at} /> · seen by {e.observed_by}
                    </div>
                  </div>
                  {e.conflict ? (
                    <Badge tone="warn">Observers disagree</Badge>
                  ) : e.success === true ? (
                    <Badge tone="good">Killed</Badge>
                  ) : e.success === false ? (
                    <Badge tone="bad">Wipe</Badge>
                  ) : (
                    <Badge>Unknown</Badge>
                  )}
                </li>
              ))}
            </ol>
          )}
        </section>
        <section>
          <SectionTitle aside={<span className="text-xs text-faint">death coverage: {deathCoverage}</span>}>Deaths and wipes</SectionTitle>
          {run.deaths.length === 0 && run.wipes.length === 0 ? (
            <p className="text-sm text-muted">
              {deathCoverage === "complete" ? "No deaths were observed." : "No deaths were recorded, but death coverage for this run is incomplete."}
            </p>
          ) : (
            <ul className="card divide-y divide-line/60 text-sm">
              {run.wipes.map((w, i) => (
                <li key={`w${i}`} className="px-4 py-2">
                  <div className="flex items-center justify-between gap-3">
                    <span>
                      <Badge tone="bad">{w.kind === "party_wipe" ? "Party wipe" : "Encounter failed"}</Badge>{" "}
                      {w.inferred && (
                        <Badge tone="warn" title={w.detail}>
                          inferred
                        </Badge>
                      )}
                    </span>
                    <span className="text-xs text-faint">
                      <Timestamp iso={w.at} />
                    </span>
                  </div>
                  <span className="block text-xs text-faint mt-1">{w.detail}</span>
                </li>
              ))}
              {run.deaths.map((d, i) => {
                const who = run.participants.find((p) => !isHidden(p.character) && p.character.id === d.character_id);
                return (
                  <li key={`d${i}`} className="px-4 py-2 flex items-center justify-between gap-3">
                    <span>{who ? <CharacterLink character={who.character} /> : <span className="text-faint italic">Hidden character</span>}</span>
                    <span className="text-xs text-faint">
                      <Timestamp iso={d.occurred_at} /> · seen by {d.observed_by}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      <section>
        <SectionTitle>Where this data comes from</SectionTitle>
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-faint border-b border-line">
              <tr>
                <th className="px-4 py-3 font-medium">Observer</th>
                <th className="px-3 py-3 font-medium">Their record</th>
                <th className="px-3 py-3 font-medium">Damage meter</th>
                <th className="px-3 py-3 font-medium">Collectors</th>
                <th className="px-4 py-3 font-medium">Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {run.sources.map((s, i) => (
                <tr key={i} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-3">{s.observer}</td>
                  <td className="px-3 py-3 text-muted">
                    {s.state.replace("_", " ")}, revision {s.revision}
                  </td>
                  <td className="px-3 py-3 text-muted">{s.meter_status ?? "not recorded"}</td>
                  <td className="px-3 py-3 text-xs text-faint">
                    {Object.entries(s.collectors)
                      .filter(([, v]) => v !== "active")
                      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
                      .join(", ") || "all active"}
                  </td>
                  <td className="px-4 py-3 text-muted">
                    <Timestamp iso={s.uploaded_at} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-faint">
          Observers are anonymous ForeverTracker users who were in this group. All values are self-reported through the addon and are not verified by Blizzard.
          Values marked <span className="text-good">✓</span> ({RESOLUTION_LABEL.corroborated.toLowerCase()}) are the most reliable.
        </p>
      </section>
    </div>
  );
}
