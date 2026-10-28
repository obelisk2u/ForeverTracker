import Link from "next/link";

import { OutcomeBadge } from "@/components/Badges";
import { Freshness } from "@/components/Freshness";
import { SearchBox } from "@/components/SearchBox";
import { SectionTitle } from "@/components/States";
import { api } from "@/lib/api";
import { formatShortDate } from "@/lib/format";
import type { ActivityItem, OverviewStats } from "@/lib/types";

export const dynamic = "force-dynamic";

function Stat({ label, value, hint }: { label: string; value: number | string; hint: string }) {
  return (
    <div className="card p-4" title={hint}>
      <div className="text-2xl font-semibold tabular text-text">{typeof value === "number" ? value.toLocaleString("en-US") : value}</div>
      <div className="text-xs uppercase tracking-wide text-faint mt-1">{label}</div>
    </div>
  );
}

export default async function HomePage() {
  let overview: OverviewStats | null = null;
  let recent: ActivityItem[] = [];
  try {
    [overview, recent] = await Promise.all([api.overview(), api.recent(8)]);
  } catch {
    // The page still explains the product when the API is unreachable.
  }
  return (
    <div className="flex flex-col gap-12">
      <section className="pt-6 md:pt-12 text-center flex flex-col items-center gap-5">
        <p className="text-xs uppercase tracking-[0.3em] text-gold">World of Warcraft: Forever</p>
        <h1 className="font-display text-4xl md:text-5xl leading-tight max-w-3xl">
          Look up anyone you have grouped with.
        </h1>
        <p className="text-muted max-w-2xl">
          ForeverTracker turns the dungeon runs recorded by its addon users into searchable character histories: who was
          there, who died, what the damage meter saw and how gear improved. A character appears here even if they never
          installed the addon, as long as someone in their group did.
        </p>
        <div className="w-full max-w-2xl">
          <SearchBox />
        </div>
        {overview?.last_observation_at && <Freshness iso={overview.last_observation_at} label="Latest observed run" />}
      </section>

      {overview && (
        <section aria-label="Featured statistics" className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Characters observed" value={overview.characters} hint="Distinct characters seen in at least one recorded run" />
          <Stat label="Dungeon runs" value={overview.runs} hint="Canonical runs after merging multiple observers" />
          <Stat label="Multi-observer runs" value={overview.reconciled_runs} hint="Runs recorded by two or more ForeverTracker users and reconciled" />
          <Stat label="Confirmed completions" value={overview.confirmed_completions} hint="Runs with an in-game completion event" />
        </section>
      )}

      <div className="grid lg:grid-cols-[3fr_2fr] gap-8">
        <section>
          <SectionTitle>Recently observed runs</SectionTitle>
          {recent.length === 0 ? (
            <p className="text-sm text-muted">No runs have been uploaded yet.</p>
          ) : (
            <ul className="card divide-y divide-line/60">
              {recent.map((r) => (
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
          )}
        </section>
        <section>
          <SectionTitle>How the data is collected</SectionTitle>
          <ol className="flex flex-col gap-3 text-sm">
            {[
              ["Play with the addon", "ForeverTracker records the dungeon runs you join: party roster, bosses, deaths and the totals from Blizzard's built-in damage meter. It makes no network requests."],
              ["Uploaded after you log out", "WoW saves addon data when you log out or type /reload, and the ForeverTracker desktop app uploads it automatically."],
              ["Records are reconciled", "When several group members upload the same run, their records are merged, deaths are de-duplicated and disagreements are kept visible."],
            ].map(([title, text], i) => (
              <li key={title} className="card p-4 flex gap-3">
                <span className="font-display text-gold text-xl leading-none">{i + 1}</span>
                <span>
                  <span className="block text-text font-medium">{title}</span>
                  <span className="text-muted">{text}</span>
                </span>
              </li>
            ))}
          </ol>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link href="/download" className="px-4 py-2 rounded-lg bg-gold text-ink font-semibold hover:bg-gold-strong focus-ring">
              Get the addon
            </Link>
            <Link href="/about" className="px-4 py-2 rounded-lg border border-line hover:bg-surface-2 focus-ring">
              What is collected
            </Link>
          </div>
        </section>
      </div>

      {overview && overview.dungeons.length > 0 && (
        <section>
          <SectionTitle>Dungeons</SectionTitle>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {overview.dungeons.map((d: Record<string, unknown>) => (
              <div key={String(d.slug)} className="card p-4">
                <div className="text-text">{String(d.name)}</div>
                <div className="text-xs text-faint">{Number(d.runs).toLocaleString("en-US")} observed runs</div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
