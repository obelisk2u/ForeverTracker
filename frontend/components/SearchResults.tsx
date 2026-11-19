import { ChevronRight } from "lucide-react";
import Link from "next/link";

import { Badge, ClassName } from "@/components/Badges";
import { characterPath } from "@/components/CharacterLink";
import { LocalTime } from "@/components/LocalTime";
import { EmptyState, Notice } from "@/components/States";
import { classColor, namespaceLabel, raceName } from "@/lib/game";
import type { CharacterSummary, SearchResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

// A square with the character's initial, tinted with their class colour.
export function Monogram({ name, classFile, className }: { name: string; classFile: string | null | undefined; className?: string }) {
  const color = classColor(classFile);
  return (
    <span
      aria-hidden="true"
      className={cn("inline-flex size-9 shrink-0 items-center justify-center rounded-lg border text-sm font-semibold", className)}
      style={{ color, backgroundColor: `color-mix(in oklch, ${color} 12%, transparent)`, borderColor: `color-mix(in oklch, ${color} 28%, transparent)` }}
    >
      {name.trim().charAt(0).toUpperCase()}
    </span>
  );
}

const ROW = "md:grid-cols-[auto_minmax(0,1fr)_8.5rem_4.5rem_6.5rem_1rem]";

// One character in a list: name in class colour, level, race, class, region, runs and last seen.
export function CharacterCard({ c, sameNameAsAnother = false }: { c: CharacterSummary; sameNameAsAnother?: boolean }) {
  return (
    <Link
      href={characterPath(c)}
      className={cn("group focus-ring grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-4 px-4 py-3 transition-colors hover:bg-accent/60", ROW)}
    >
      <Monogram name={c.name || c.full_name} classFile={c.class_file} />
      <span className="min-w-0">
        <span className="flex items-center gap-2">
          <span className="truncate font-medium" style={{ color: classColor(c.class_file) }}>
            {c.full_name}
          </span>
          {sameNameAsAnother && <span className="shrink-0 text-xs text-warning">same name as another result</span>}
          {c.identity_confidence !== "guid_confirmed" && (
            <Badge tone="warn" title="Identified by name only; may be less reliable">
              Name only
            </Badge>
          )}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          Level {c.latest_level ?? "?"} {raceName(c.race_file)} <ClassName classFile={c.class_file} />
          <span className="md:hidden"> · {namespaceLabel(c.namespace)}</span>
        </span>
      </span>
      <span className="hidden text-sm text-muted-foreground md:block">{namespaceLabel(c.namespace)}</span>
      <span className="text-right text-sm text-muted-foreground tabular md:text-left">
        {c.runs_observed} run{c.runs_observed === 1 ? "" : "s"}
      </span>
      <LocalTime iso={c.last_observed_at} format="relative" className="hidden text-sm text-faint md:block" />
      <ChevronRight aria-hidden="true" className="hidden size-4 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-foreground md:block" />
    </Link>
  );
}

// The frame around a list of CharacterCards, with column labels on wide screens.
export function CharacterTable({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div aria-hidden="true" className={cn("hidden items-center gap-x-4 border-b px-4 py-2.5 text-xs font-medium text-muted-foreground md:grid", ROW)}>
        <span className="w-9" />
        <span>Character</span>
        <span>Region</span>
        <span>Runs</span>
        <span>Last seen</span>
        <span />
      </div>
      {children}
    </div>
  );
}

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
      <p className="text-sm text-muted-foreground">
        {data.total} character{data.total === 1 ? "" : "s"} found{data.exact ? " (exact name)" : ""}.
      </p>
      {data.duplicate_names.length > 0 && (
        <Notice tone="warn">
          Several characters share the name {data.duplicate_names.map((n) => `“${n}”`).join(", ")}. They are listed separately
          because nothing proves they are the same character (different regions or rulesets, or a name that changed hands).
        </Notice>
      )}
      <CharacterTable>
        <ul className="divide-y">
          {data.results.map((c) => (
            <li key={c.id}>
              <CharacterCard c={c} sameNameAsAnother={dupes.has(c.full_name.toLowerCase())} />
            </li>
          ))}
        </ul>
      </CharacterTable>
    </div>
  );
}
