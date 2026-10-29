import Link from "next/link";

import { ClassName, IdentityBadge } from "@/components/Badges";
import { Freshness } from "@/components/Freshness";
import { RunHistoryTable } from "@/components/RunHistoryTable";
import { StatGrid } from "@/components/StatGrid";
import { EmptyState, Notice, Pagination, SectionTitle } from "@/components/States";
import { formatNumericDate, formatShortDate } from "@/lib/format";
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
  const byDungeon = (profile.stats.by_dungeon ?? []) as Array<{
    dungeon: { slug: string; name: string };
    runs: number;
    completions_confirmed: number;
    deaths_per_run_mean: { value: number | null; sample_size: number };
  }>;
  return (
    <div className="flex flex-col gap-8">
      <header className="card p-6 relative overflow-hidden">
        <div
          aria-hidden="true"
          className="absolute inset-y-0 left-0 w-1.5"
          style={{ background: `linear-gradient(${classColor(c.class_file)}, transparent)` }}
        />
        <h1 className="font-display text-3xl md:text-4xl" style={{ color: classColor(c.class_file) }}>
          {c.full_name}
        </h1>
        <p className="mt-1 text-muted">
          Level <span className="text-text">{c.latest_level ?? "?"}</span> {raceName(c.race_file)} <ClassName classFile={c.class_file} />
          {" · "}
          {namespaceLabel(c.namespace)}
          {profile.realm_label && <span className="text-faint"> · realm label “{profile.realm_label}”</span>}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <IdentityBadge confidence={c.identity_confidence} />
          <Freshness iso={profile.freshness.last_observed_at} />
          <span className="text-sm text-muted">
            · first observed <time dateTime={c.first_observed_at}>{formatNumericDate(c.first_observed_at)}</time>
          </span>
        </div>
      </header>

      {profile.notices.length > 0 && (
        <div className="flex flex-col gap-2">
          {profile.notices.map((n) => (
            <Notice key={n}>{n}</Notice>
          ))}
        </div>
      )}

      <section>
        <SectionTitle>Summary</SectionTitle>
        <StatGrid stats={profile.stats} />
      </section>

      <section>
        <SectionTitle>Dungeon history</SectionTitle>
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
        <section>
          <SectionTitle>By dungeon</SectionTitle>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {byDungeon.map((d) => (
              <Link
                key={d.dungeon.slug}
                href={`${profile.canonical_path}?dungeon=${d.dungeon.slug}`}
                className="card p-4 hover:border-gold-dim focus-ring"
              >
                <div className="text-text font-medium">{d.dungeon.name}</div>
                <div className="text-sm text-muted mt-1">
                  {d.runs} run{d.runs === 1 ? "" : "s"} · {d.completions_confirmed} confirmed
                </div>
                <div className="text-xs text-faint mt-1">
                  Deaths/run:{" "}
                  {d.deaths_per_run_mean.value === null ? "—" : d.deaths_per_run_mean.value.toFixed(2)} (n={d.deaths_per_run_mean.sample_size})
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {profile.name_history.length > 1 && (
        <section>
          <SectionTitle>Name history</SectionTitle>
          <ul className="text-sm text-muted">
            {profile.name_history.map((n) => (
              <li key={n.full_name}>
                <span className="text-text">{n.full_name}</span> · seen {formatShortDate(n.first_seen_at)} – {formatShortDate(n.last_seen_at)}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
