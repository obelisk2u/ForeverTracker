import { ChevronRight } from "lucide-react";
import Link from "next/link";

import { ClassName, IdentityBadge } from "@/components/Badges";
import { Freshness } from "@/components/Freshness";
import { LocalTime } from "@/components/LocalTime";
import { RunHistoryTable } from "@/components/RunHistoryTable";
import { Monogram } from "@/components/SearchResults";
import { StatGrid } from "@/components/StatGrid";
import { EmptyState, Notice, Pagination, SectionTitle } from "@/components/States";
import { classColor, namespaceLabel, raceName } from "@/lib/game";
import type { CharacterProfile, RunHistoryResponse } from "@/lib/types";

export function CharacterProfileView({
  profile,
  history,
  page,
  filterQuery = "",
}: {
  profile: CharacterProfile;
  history: RunHistoryResponse;
  page: number;
  filterQuery?: string;
}) {
  const c = profile.character;
  const color = classColor(c.class_file);
  const byDungeon = (profile.stats.by_dungeon ?? []) as Array<{
    dungeon: { slug: string; name: string };
    runs: number;
    completions_confirmed: number;
    deaths_per_run_mean: { value: number | null; sample_size: number };
  }>;
  const mostRuns = Math.max(1, ...byDungeon.map((d) => d.runs));
  return (
    <div className="flex flex-col gap-10">
      <header className="relative flex flex-col gap-5 border-b pb-6 sm:flex-row sm:items-center">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-10 left-0 h-40 w-[28rem] max-w-full opacity-60 blur-3xl"
          style={{ background: `radial-gradient(closest-side, color-mix(in oklch, ${color} 18%, transparent), transparent)` }}
        />
        <Monogram name={c.name || c.full_name} classFile={c.class_file} className="relative size-16 rounded-xl text-2xl" />
        <div className="relative min-w-0">
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl" style={{ color }}>
            {c.full_name}
          </h1>
          <p className="mt-1 text-muted-foreground">
            Level <span className="text-foreground">{c.latest_level ?? "?"}</span> {raceName(c.race_file)} <ClassName classFile={c.class_file} />
            {" · "}
            {namespaceLabel(c.namespace)}
            {profile.realm_label && <span className="text-faint"> · realm label “{profile.realm_label}”</span>}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            <IdentityBadge confidence={c.identity_confidence} />
            <Freshness iso={profile.freshness.last_observed_at} />
            <span className="text-sm text-muted-foreground">
              First observed <LocalTime iso={c.first_observed_at} format="numeric" />
            </span>
          </div>
        </div>
      </header>

      {profile.notices.length > 0 && (
        <div className="flex flex-col gap-2">
          {profile.notices.map((n) => (
            <Notice key={n}>{n}</Notice>
          ))}
        </div>
      )}

      <section aria-labelledby="summary">
        <SectionTitle id="summary">Summary</SectionTitle>
        <StatGrid stats={profile.stats} />
      </section>

      <section aria-labelledby="history">
        <SectionTitle id="history">Dungeon history</SectionTitle>
        {history.items.length === 0 ? (
          <EmptyState title="No runs match">Try removing a filter.</EmptyState>
        ) : (
          <>
            <RunHistoryTable rows={history.items} characterId={c.id} />
            <Pagination
              page={page}
              pageSize={history.page_size}
              total={history.total}
              href={(p) => `${profile.canonical_path}?page=${p}${filterQuery}`}
            />
          </>
        )}
      </section>

      {byDungeon.length > 0 && (
        <section aria-labelledby="by-dungeon">
          <SectionTitle id="by-dungeon">By dungeon</SectionTitle>
          <ul className="grid gap-1 rounded-xl border bg-card p-1.5 sm:grid-cols-2 lg:grid-cols-3">
            {byDungeon.map((d) => (
              <li key={d.dungeon.slug}>
                <Link
                  href={`${profile.canonical_path}?dungeon=${d.dungeon.slug}`}
                  className="group focus-ring block rounded-md px-2.5 py-2 transition-colors hover:bg-accent/60"
                >
                  <span className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="truncate text-foreground">{d.dungeon.name}</span>
                    <span className="text-muted-foreground tabular">{d.runs}</span>
                  </span>
                  <span aria-hidden="true" className="mt-1.5 block h-1 rounded-full bg-muted">
                    <span className="block h-1 rounded-full" style={{ width: `${(d.runs / mostRuns) * 100}%`, backgroundColor: color }} />
                  </span>
                  <span className="mt-1.5 flex items-center justify-between text-xs text-faint">
                    <span>
                      {d.completions_confirmed} confirmed ·{" "}
                      {d.deaths_per_run_mean.value === null
                        ? "deaths/run —"
                        : `${d.deaths_per_run_mean.value.toFixed(2)} deaths/run (n=${d.deaths_per_run_mean.sample_size})`}
                    </span>
                    <ChevronRight aria-hidden="true" className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {profile.name_history.length > 1 && (
        <section aria-labelledby="names">
          <SectionTitle id="names">Name history</SectionTitle>
          <ul className="divide-y rounded-xl border bg-card text-sm">
            {profile.name_history.map((n) => (
              <li key={n.full_name} className="flex justify-between gap-3 px-4 py-2.5">
                <span className="text-foreground">{n.full_name}</span>
                <span className="text-muted-foreground">
                  <LocalTime iso={n.first_seen_at} format="short" /> – <LocalTime iso={n.last_seen_at} format="short" />
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
