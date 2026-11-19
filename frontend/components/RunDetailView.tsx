import { Calendar, ChevronRight, Flag, Gauge, Globe, RefreshCw, Skull, Timer } from "lucide-react";
import Link from "next/link";

import { Badge, OutcomeBadge } from "@/components/Badges";
import { CharacterLink } from "@/components/CharacterLink";
import { Timestamp } from "@/components/Freshness";
import { LocalTime } from "@/components/LocalTime";
import { PartyStats } from "@/components/PartyStats";
import { RunGear } from "@/components/RunGear";
import { Notice, SectionTitle } from "@/components/States";
import { formatDuration, formatOffset, relativeTime } from "@/lib/format";
import { namespaceLabel } from "@/lib/game";
import { isHidden, type EncounterOut, type RunDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

function Meta({ icon: Icon, label, children }: { icon: typeof Calendar; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <Icon aria-hidden="true" className="size-4 text-faint" />
      <dt className="sr-only">{label}</dt>
      <dd className="text-foreground">{children}</dd>
    </div>
  );
}

function encounterState(e: EncounterOut): { text: string; marker: string; tone: string } {
  if (e.conflict) return { text: "Observers disagree", marker: "border-warning", tone: "text-warning" };
  if (e.success === true) return { text: "Killed", marker: "border-primary bg-primary", tone: "text-muted-foreground" };
  if (e.success === false) return { text: "Wipe", marker: "border-destructive", tone: "text-destructive" };
  return { text: "Unknown", marker: "border-faint", tone: "text-faint" };
}

// The bosses in pull order, on a line from the start of the run.
function BossTimeline({ run }: { run: RunDetail }) {
  if (run.encounters.length === 0) return <p className="text-sm text-muted-foreground">No boss encounters were recorded.</p>;
  return (
    <ol className="grid gap-x-2 gap-y-4 rounded-xl border bg-card p-4 sm:grid-cols-[repeat(auto-fit,minmax(9rem,1fr))]">
      {run.encounters.map((e, i) => {
        const s = encounterState(e);
        return (
          <li key={i} className="relative flex gap-3 sm:flex-col sm:gap-2.5">
            {i < run.encounters.length - 1 && (
              <span aria-hidden="true" className="absolute top-[5px] left-5 hidden h-px w-[calc(100%-0.75rem)] bg-border sm:block" />
            )}
            <span aria-hidden="true" className={cn("relative mt-1 size-2.5 shrink-0 rotate-45 rounded-[2px] border-[1.5px] sm:mt-0 sm:ml-0.5", s.marker)} />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-foreground">{e.name ?? `Encounter ${e.encounter_id}`}</div>
              <div className="mt-0.5 flex items-center gap-1.5 text-xs">
                <LocalTime iso={e.started_at} className="font-mono text-faint">
                  {formatOffset(run.started_at, e.started_at)}
                </LocalTime>
                <span className={s.tone}>{s.text}</span>
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// Deaths and wipes together, in the order they happened.
function Casualties({ run }: { run: RunDetail }) {
  const deathCoverage = String(run.coverage.deaths ?? "none");
  if (run.deaths.length === 0 && run.wipes.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {deathCoverage === "complete" ? "No deaths were observed." : "No deaths were recorded, but death coverage for this run is incomplete."}
      </p>
    );
  }
  const bossName = new Map(run.encounters.map((e) => [e.encounter_id, e.name ?? `Encounter ${e.encounter_id}`]));
  const events = [
    ...run.wipes.map((w, i) => ({ at: w.at, key: `w${i}`, node: (
      <>
        <Flag aria-hidden="true" className="size-4 shrink-0 text-destructive" />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium text-destructive">{w.kind === "party_wipe" ? "Party wipe" : "Encounter failed"}</span>
            {w.inferred && (
              <Badge tone="warn" title={w.detail}>
                inferred
              </Badge>
            )}
          </span>
          <span className="block text-xs text-faint">{w.detail}</span>
        </span>
      </>
    ) })),
    ...run.deaths.map((d, i) => {
      const who = run.participants.find((p) => !isHidden(p.character) && p.character.id === d.character_id);
      const during = d.encounter_id !== null ? bossName.get(d.encounter_id) : undefined;
      return { at: d.occurred_at, key: `d${i}`, node: (
        <>
          <Skull aria-hidden="true" className="size-4 shrink-0 text-faint" />
          <span className="min-w-0 flex-1">
            {who ? <CharacterLink character={who.character} showDot={false} /> : <span className="text-faint italic">Hidden character</span>}
            {during && <span className="text-xs text-faint"> · during {during}</span>}
          </span>
        </>
      ) };
    }),
  ].sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  return (
    <ul className="divide-y rounded-xl border bg-card text-sm">
      {events.map((ev) => (
        <li key={ev.key} className="flex items-center gap-3 px-4 py-2.5">
          {ev.node}
          <LocalTime iso={ev.at} className="shrink-0 font-mono text-xs text-faint">
            {formatOffset(run.started_at, ev.at)}
          </LocalTime>
        </li>
      ))}
    </ul>
  );
}

export function RunDetailView({ run }: { run: RunDetail }) {
  const deathCoverage = String(run.coverage.deaths ?? "none");
  const unidentified = Number(run.coverage.roster_entries_unidentified ?? 0);
  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-4 border-b pb-6">
        <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-muted-foreground">
          <Link href="/runs" className="focus-ring rounded-sm hover:text-foreground">
            Runs
          </Link>
          <ChevronRight aria-hidden="true" className="size-3.5 text-faint" />
          <Link href={`/runs?dungeon=${encodeURIComponent(run.dungeon.slug)}`} className="focus-ring truncate rounded-sm hover:text-foreground">
            {run.dungeon.name}
          </Link>
          <ChevronRight aria-hidden="true" className="size-3.5 text-faint" />
          <span className="font-mono text-xs text-faint">{run.run_id}</span>
        </nav>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground md:text-4xl">{run.dungeon.name}</h1>
          <OutcomeBadge outcome={run.outcome} confidence={run.completion_confidence} />
          {run.match_status === "reconciled" && (
            <Badge tone="gold" title="Several ForeverTracker users recorded this run; their records were merged">
              Reconciled from {run.contributor_count} observers
            </Badge>
          )}
          {run.match_status === "unresolved" && (
            <Badge tone="warn" title="This record might belong to another run; kept separate pending review">
              Unresolved match
            </Badge>
          )}
        </div>
        <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <Meta icon={Calendar} label="Started">
            <Timestamp iso={run.started_at} />
          </Meta>
          <Meta icon={Timer} label="Duration">
            <span className="tabular">{run.ended_at ? formatDuration(run.duration_seconds) : "still in progress"}</span>
          </Meta>
          {run.difficulty_name && (
            <Meta icon={Gauge} label="Difficulty">
              {run.difficulty_name}
            </Meta>
          )}
          <Meta icon={Globe} label="Namespace">
            {namespaceLabel(run.namespace.slug)}
          </Meta>
          <Meta icon={RefreshCw} label="Last updated">
            <LocalTime iso={run.last_observed_at} className="text-muted-foreground">
              updated {relativeTime(run.last_observed_at)}
            </LocalTime>
          </Meta>
        </dl>
        {run.is_synthetic && <Notice tone="warn">Synthetic development run generated by the simulator.</Notice>}
        {run.outcome !== "completed" && (run.outcome === "left" || run.outcome === "disconnected" || run.outcome === "unknown") && (
          <p className="max-w-3xl text-sm text-muted-foreground">
            {run.outcome === "unknown"
              ? "No completion event was recorded, so the outcome is unknown."
              : "The observers left before any completion event. That does not mean the group failed; ForeverTracker never infers a completion from leaving an instance."}
          </p>
        )}
      </header>

      <section aria-labelledby="bosses">
        <SectionTitle id="bosses">Bosses</SectionTitle>
        <BossTimeline run={run} />
      </section>

      <section aria-labelledby="party">
        <SectionTitle id="party">Party</SectionTitle>
        <PartyStats participants={run.participants} encounters={run.encounters} deaths={run.deaths} />
        {unidentified > 0 && (
          <p className="mt-3 text-xs text-faint">
            {unidentified} roster entr{unidentified === 1 ? "y" : "ies"} could not be identified safely (secret or ambiguous identity) and{" "}
            {unidentified === 1 ? "is" : "are"} not shown.
          </p>
        )}
        {run.passed_through.length > 0 && (
          <p className="mt-3 text-xs text-faint">
            Also in the group for a moment:{" "}
            {run.passed_through.map((p, i) => (
              <span key={i}>
                {i > 0 && ", "}
                <CharacterLink character={p.character} showDot={false} /> ({formatDuration(p.seconds)})
              </span>
            ))}
            . They left before any boss fight and are not counted in this run.
          </p>
        )}
      </section>

      <div className="grid gap-10 lg:grid-cols-2">
        <section aria-labelledby="deaths">
          <SectionTitle id="deaths" aside={`Death coverage: ${deathCoverage}`}>
            Deaths and wipes
          </SectionTitle>
          <Casualties run={run} />
        </section>
        <section aria-labelledby="gear">
          <SectionTitle id="gear">Gear</SectionTitle>
          <RunGear participants={run.participants} />
        </section>
      </div>
    </div>
  );
}
