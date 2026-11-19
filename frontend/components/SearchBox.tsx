"use client";

import { CornerDownLeft, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { ClassDot } from "@/components/Badges";
import { characterPath } from "@/components/CharacterLink";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { apiBase } from "@/lib/api";
import { className, classColor, namespaceLabel } from "@/lib/game";
import type { CharacterSummary, SearchResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const NAMESPACES = [
  { value: "", label: "All regions" },
  { value: "us-pve", label: "US · Normal" },
  { value: "us-hardcore", label: "US · Hardcore" },
  { value: "us-pvp", label: "US · PvP" },
  { value: "us-rp", label: "US · Roleplay" },
  { value: "eu-pve", label: "EU · Normal" },
  { value: "eu-hardcore", label: "EU · Hardcore" },
  { value: "eu-pvp", label: "EU · PvP" },
  { value: "eu-rp", label: "EU · Roleplay" },
];

const SUGGESTIONS = 6;
const DEBOUNCE_MS = 150;

// Characters matching what has been typed so far, ranked like the search page (exact and prefix
// matches first). A failed request just means no suggestions.
async function suggest(q: string, namespace: string, signal: AbortSignal): Promise<CharacterSummary[]> {
  const params = new URLSearchParams({ q, page_size: String(SUGGESTIONS) });
  if (namespace) params.set("namespace", namespace);
  try {
    const res = await fetch(`${apiBase()}/api/v1/search?${params.toString()}`, { signal });
    return res.ok ? ((await res.json()) as SearchResponse).results : [];
  } catch {
    return [];
  }
}

export function SearchBox({
  compact = false,
  initialQuery = "",
  initialNamespace = "",
}: {
  compact?: boolean;
  initialQuery?: string;
  initialNamespace?: string;
}) {
  const router = useRouter();
  const listId = useId();
  const [query, setQuery] = useState(initialQuery);
  const [namespace, setNamespace] = useState(initialNamespace);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<CharacterSummary[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const input = useRef<HTMLInputElement>(null);

  // "/" jumps to the header search from anywhere that is not already a text field.
  useEffect(() => {
    if (!compact) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      e.preventDefault();
      input.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [compact]);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setSuggestions([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      const found = await suggest(q, namespace, controller.signal);
      if (!controller.signal.aborted) {
        setSuggestions(found);
        setActive(-1);
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, namespace]);

  // The suggestions, then "See all results" for the full search page.
  const options = suggestions.length > 0 ? suggestions.length + 1 : 0;
  const showList = open && options > 0;

  function searchAll() {
    const q = query.trim();
    if (q.length < 2) {
      setError("Type at least 2 characters of a character name.");
      return;
    }
    setError(null);
    setOpen(false);
    const params = new URLSearchParams({ q });
    if (namespace) params.set("namespace", namespace);
    router.push(`/search?${params.toString()}`);
  }

  function choose(index: number) {
    setOpen(false);
    const c = suggestions[index];
    if (c) router.push(characterPath(c));
    else searchAll();
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (showList && active >= 0) choose(active);
    else searchAll();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" && options > 0) {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, options - 1));
    } else if (e.key === "ArrowUp" && showList) {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, -1));
    } else if (e.key === "Escape" && showList) {
      e.preventDefault();
      setOpen(false);
    }
  }

  const optionId = (i: number) => `${listId}-${i}`;
  const inputId = compact ? "search-compact" : "search-main";

  return (
    <form role="search" onSubmit={submit} className="w-full">
      <div className={cn("flex items-stretch gap-2", !compact && "flex-col sm:flex-row")}>
        <label className="sr-only" htmlFor={inputId}>
          Character name
        </label>
        <div className="relative flex min-w-0 flex-1">
          <Search
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute top-1/2 -translate-y-1/2 text-faint",
              compact ? "left-2.5 size-3.5" : "left-3.5 size-4",
            )}
          />
          <Input
            ref={input}
            id={inputId}
            type="search"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={showList}
            aria-controls={listId}
            aria-activedescendant={showList && active >= 0 ? optionId(active) : undefined}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onKeyDown={onKeyDown}
            placeholder={compact ? "Search characters" : "Character name, e.g. Asha Brightvale"}
            maxLength={64}
            autoComplete="off"
            className={cn(
              "[&::-webkit-search-cancel-button]:hidden",
              compact ? "h-8 pr-8 pl-8 text-sm" : "h-11 pl-10 text-base md:text-base",
            )}
          />
          {compact && (
            <Kbd className="absolute top-1/2 right-1.5 -translate-y-1/2 border bg-background font-mono" aria-hidden="true">
              /
            </Kbd>
          )}
          {showList && (
            <ul
              id={listId}
              role="listbox"
              aria-label="Matching characters"
              className={cn(
                "absolute top-full z-50 mt-1.5 overflow-hidden rounded-lg border bg-popover p-1 text-left shadow-2xl shadow-black/50",
                compact ? "right-0 w-[min(22rem,calc(100vw-2rem))]" : "right-0 left-0",
              )}
            >
              {suggestions.map((c, i) => (
                <li
                  key={c.id}
                  id={optionId(i)}
                  role="option"
                  aria-selected={i === active}
                  // Keep focus in the input so the list does not close before the click lands.
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(i)}
                  onMouseEnter={() => setActive(i)}
                  className={cn("flex cursor-pointer items-center gap-3 rounded-md px-2.5 py-2", i === active && "bg-accent")}
                >
                  <ClassDot classFile={c.class_file} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium" style={{ color: classColor(c.class_file) }}>
                      {c.full_name}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {className(c.class_file)} · {namespaceLabel(c.namespace)}
                    </div>
                  </div>
                  <span className="shrink-0 text-xs text-faint tabular">
                    {c.runs_observed} run{c.runs_observed === 1 ? "" : "s"}
                  </span>
                </li>
              ))}
              <li
                id={optionId(suggestions.length)}
                role="option"
                aria-selected={active === suggestions.length}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(suggestions.length)}
                onMouseEnter={() => setActive(suggestions.length)}
                className={cn(
                  "mt-1 flex cursor-pointer items-center gap-2 rounded-md border-t px-2.5 py-2 text-sm text-muted-foreground",
                  active === suggestions.length && "bg-accent text-foreground",
                )}
              >
                <CornerDownLeft aria-hidden="true" className="size-3.5" />
                See all results for “{query.trim()}”
              </li>
            </ul>
          )}
        </div>
        {!compact && (
          <>
            <label className="sr-only" htmlFor="search-namespace">
              Region and ruleset
            </label>
            <NativeSelect
              id="search-namespace"
              value={namespace}
              onChange={(e) => setNamespace(e.target.value)}
              className="w-full sm:w-auto [&_select]:h-11 [&_select]:pr-9 [&_select]:pl-3"
            >
              {NAMESPACES.map((n) => (
                <NativeSelectOption key={n.value} value={n.value}>
                  {n.label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <Button type="submit" className="h-11 px-5 text-sm font-semibold">
              Search
            </Button>
          </>
        )}
      </div>
      {error && !compact && (
        <p role="alert" className="mt-2 text-sm text-warning">
          {error}
        </p>
      )}
    </form>
  );
}
