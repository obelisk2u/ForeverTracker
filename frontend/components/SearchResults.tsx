import Link from "next/link";

import { ClassName, IdentityBadge } from "@/components/Badges";
import { characterPath } from "@/components/CharacterLink";
import { EmptyState, Notice } from "@/components/States";
import { relativeTime } from "@/lib/format";
import { classColor, namespaceLabel, raceName } from "@/lib/game";
import type { SearchResponse } from "@/lib/types";

export function SearchResults({ data }: { data: SearchResponse }) {
  if (data.results.length === 0) {
    return (
      <EmptyState title={`No characters match “${data.query}”`}>
        ForeverTracker only knows characters that appeared in a run recorded by one of its addon users. Check the
        spelling, try part of the name, or remove the region filter.
      </EmptyState>
    );
  }
  const dupes = new Set(data.duplicate_names.map((n) => n.toLowerCase()));
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted">
        {data.total} character{data.total === 1 ? "" : "s"} found{data.exact ? " (exact name)" : ""}.
      </p>
      {data.duplicate_names.length > 0 && (
        <Notice tone="warn">
          Several characters share the name {data.duplicate_names.map((n) => `“${n}”`).join(", ")}. They are listed separately
          because nothing proves they are the same character (different regions or rulesets, or a name that changed hands).
        </Notice>
      )}
      <ul className="flex flex-col gap-2">
        {data.results.map((c) => (
          <li key={c.id}>
            <Link href={characterPath(c)} className="card p-4 flex flex-wrap items-center justify-between gap-3 hover:border-gold-dim focus-ring">
              <div className="min-w-0">
                <div className="text-lg font-medium truncate" style={{ color: classColor(c.class_file) }}>
                  {c.full_name}
                  {dupes.has(c.full_name.toLowerCase()) && <span className="ml-2 text-xs text-warn align-middle">same name as another result</span>}
                </div>
                <div className="text-sm text-muted">
                  Level {c.latest_level ?? "?"} {raceName(c.race_file)} <ClassName classFile={c.class_file} /> · {namespaceLabel(c.namespace)}
                </div>
              </div>
              <div className="flex items-center gap-3 text-sm text-muted">
                <IdentityBadge confidence={c.identity_confidence} />
                <span>{c.runs_observed} runs</span>
                <span className="text-faint">seen {relativeTime(c.last_observed_at)}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
