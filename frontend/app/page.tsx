import { ArrowRight, ArrowUpRight, Eye, Skull } from "lucide-react";
import Link from "next/link";

import { ClassDot, OutcomeBadge, RoleIcon } from "@/components/Badges";
import { BossPips } from "@/components/BossPips";
import { characterPath } from "@/components/CharacterLink";
import { Freshness } from "@/components/Freshness";
import { RunList } from "@/components/RunList";
import { SearchBox } from "@/components/SearchBox";
import { SectionTitle } from "@/components/States";
import { buttonVariants } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatDuration, relativeTime } from "@/lib/format";
import { classColor, namespaceLabel } from "@/lib/game";
import { isHidden, type ActivityItem, type OverviewStats, type RunDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

function Stat({
  label,
  value,
  sub,
  href,
  icon,
}: {
  label: string;
  value: number;
  sub: string;
  href?: string;
  icon?: React.ReactNode;
}) {
  const body = (
    <>
      <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {icon}
        {label}
        {href && <ArrowUpRight aria-hidden="true" className="size-3.5 text-faint transition-colors group-hover:text-foreground" />}
      </span>
      <span className="mt-2 block text-3xl font-semibold tracking-tight text-foreground">{value.toLocaleString("en-US")}</span>
      <span className="mt-1 block text-xs text-faint">{sub}</span>
    </>
  );
  const cls = "group block bg-card p-5 transition-colors";
  return href ? (
    <Link href={href} className={cn(cls, "focus-ring hover:bg-accent")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

// The newest run, shown as it is on its own page: who was there and how the bosses went.
function LatestRun({ run }: { run: RunDetail }) {
  const party = run.participants.slice(0, 5);
  return (
    <Link
      href={`/runs/${run.run_id}`}
      className="group focus-ring block overflow-hidden rounded-xl border bg-card shadow-2xl shadow-black/30 transition-colors hover:border-foreground/20 hover:bg-accent/30"
    >
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <span className="text-xs font-medium text-muted-foreground">Latest run · {relativeTime(run.started_at)}</span>
        <OutcomeBadge outcome={run.outcome} confidence={run.completion_confidence} />
      </div>
      <div className="px-4 pt-4">
        <div className="text-lg font-semibold tracking-tight">{run.dungeon.name}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          {run.ended_at ? formatDuration(run.duration_seconds) : "In progress"}
          {run.difficulty_name && ` · ${run.difficulty_name}`} · {namespaceLabel(run.namespace.slug)}
        </div>
      </div>
      <ul className="mt-3 px-2">
        {party.map((p, i) => (
          <li key={i} className="flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm">
            <RoleIcon role={p.role} />
            {isHidden(p.character) ? (
              <span className="min-w-0 flex-1 truncate text-faint italic">Hidden character</span>
            ) : (
              <span className="min-w-0 flex-1 truncate" style={{ color: classColor(p.class_file) }}>
                {p.character.full_name}
              </span>
            )}
            {p.was_observer && (
              <span title="Recorded this run with ForeverTracker">
                <Eye aria-label="ForeverTracker user" className="size-3.5 text-primary" />
              </span>
            )}
            <span className="w-10 text-right text-xs text-faint tabular">{p.level ? `Lv ${p.level}` : ""}</span>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex items-center justify-between gap-3 border-t px-4 py-3">
        <BossPips encounters={run.encounters} />
        <span className="inline-flex items-center gap-1 text-sm text-foreground transition-colors group-hover:text-primary">
          Open run <ArrowRight aria-hidden="true" className="size-3.5 transition-transform group-hover:translate-x-0.5" />
        </span>
      </div>
    </Link>
  );
}

const STEPS = [
  [
    "Play with the addon",
    "ForeverTracker records the dungeon runs you join: party roster, bosses, deaths and the totals from Blizzard's built-in damage meter. It makes no network requests.",
  ],
  [
    "Uploaded after you log out",
    "WoW saves addon data when you log out or type /reload, and the ForeverTracker companion app uploads it automatically.",
  ],
  [
    "Records are reconciled",
    "When several group members upload the same run, their records are merged, deaths are de-duplicated and disagreements are kept visible.",
  ],
];

export default async function HomePage() {
  let overview: OverviewStats | null = null;
  let recent: ActivityItem[] = [];
  let latest: RunDetail | null = null;
  try {
    [overview, recent] = await Promise.all([api.overview(), api.recent(8)]);
    if (recent[0]) latest = await api.run(recent[0].run_id);
  } catch {
    // The page still explains the product when the API is unreachable.
  }
  const dungeons = (overview?.dungeons ?? []) as Array<{ slug: string; name: string; runs: number }>;
  const busiest = Math.max(1, ...dungeons.map((d) => d.runs));
  const faces = (latest?.participants ?? []).flatMap((p) => (isHidden(p.character) ? [] : [p.character])).slice(0, 3);

  return (
    <div className="flex flex-col gap-14">
      <section className="grid items-center gap-10 pt-2 lg:grid-cols-[minmax(0,1fr)_24rem] lg:pt-8">
        <div className="flex flex-col items-start gap-6">
          {overview?.last_observation_at && (
            <span className="rounded-full border bg-card px-3 py-1">
              <Freshness iso={overview.last_observation_at} label="Latest observed run" />
            </span>
          )}
          <div>
            <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance md:text-5xl">
              <span className="block">Track your dungeon runs.</span>
              <span className="block text-muted-foreground">Look up anyone you&apos;ve grouped with.</span>
            </h1>
            <p className="mt-4 max-w-xl text-lg leading-relaxed text-muted-foreground">
              The ForeverTracker addon records your World of Warcraft: Forever dungeon runs: who was there, who died, what
              the damage meter saw and how gear improved. Everyone in them gets a history you can search.
            </p>
          </div>
          <div className="w-full max-w-2xl">
            <SearchBox />
            {faces.length > 0 && (
              <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-faint">
                Recently seen
                {faces.map((c) => (
                  <Link key={c.id} href={characterPath(c)} className="focus-ring inline-flex items-center gap-1.5 rounded-sm hover:underline">
                    <ClassDot classFile={c.class_file} />
                    <span style={{ color: classColor(c.class_file) }}>{c.full_name}</span>
                  </Link>
                ))}
              </p>
            )}
          </div>
          <p className="max-w-xl text-sm text-faint">
            A character appears here even if they never installed the addon, as long as someone in their group did.
          </p>
        </div>
        {latest && <LatestRun run={latest} />}
      </section>

      {overview && (
        <section aria-label="Featured statistics" className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border md:grid-cols-4">
          <Stat label="Characters observed" value={overview.characters} sub="Seen in at least one recorded run" href="/characters" />
          <Stat label="Dungeon runs" value={overview.runs} sub={`${overview.runs_last_7_days.toLocaleString("en-US")} in the last 7 days`} href="/runs" />
          <Stat label="Multi-observer runs" value={overview.reconciled_runs} sub="Recorded by several players and merged" />
          <Stat
            label="Deaths observed"
            value={overview.observed_deaths}
            sub="Across every recorded run"
            icon={<Skull aria-hidden="true" className="size-3.5 text-faint" />}
          />
        </section>
      )}

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section>
          <SectionTitle
            aside={
              overview && overview.runs > recent.length ? (
                <Link href="/runs" className="focus-ring inline-flex items-center gap-1 rounded-sm hover:text-foreground">
                  All {overview.runs.toLocaleString("en-US")} runs <ArrowRight aria-hidden="true" className="size-3" />
                </Link>
              ) : undefined
            }
          >
            Recently observed runs
          </SectionTitle>
          {recent.length === 0 ? <p className="text-sm text-muted-foreground">No runs have been uploaded yet.</p> : <RunList runs={recent} />}
        </section>

        {dungeons.length > 0 && (
          <section>
            <SectionTitle aside="Runs">Dungeons</SectionTitle>
            <ul className="rounded-xl border bg-card p-1.5">
              {dungeons.map((d) => (
                <li key={d.slug}>
                  <Link
                    href={`/runs?dungeon=${encodeURIComponent(d.slug)}`}
                    className="focus-ring block rounded-md px-2.5 py-2 transition-colors hover:bg-accent/60"
                  >
                    <span className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="truncate text-foreground">{d.name}</span>
                      <span className="text-muted-foreground tabular">{d.runs.toLocaleString("en-US")}</span>
                    </span>
                    <span aria-hidden="true" className="mt-1.5 block h-1 rounded-full bg-muted">
                      <span className="block h-1 rounded-full bg-primary/70" style={{ width: `${(d.runs / busiest) * 100}%` }} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <section className="border-t pt-10">
        <div className="grid gap-8 md:grid-cols-[16rem_minmax(0,1fr)]">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">How the data is collected</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link href="/download" className={buttonVariants({ size: "lg" })}>
                Get the addon
              </Link>
              <Link href="/about" className={buttonVariants({ variant: "outline", size: "lg" })}>
                What is collected
              </Link>
            </div>
          </div>
          <ol className="grid gap-6 sm:grid-cols-3">
            {STEPS.map(([title, text], i) => (
              <li key={title} className="flex flex-col gap-2">
                <span className="font-mono text-xs text-primary">0{i + 1}</span>
                <span className="font-medium text-foreground">{title}</span>
                <span className="text-sm leading-relaxed text-muted-foreground">{text}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  );
}
