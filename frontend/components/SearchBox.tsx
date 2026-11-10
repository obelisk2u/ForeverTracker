"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { characterPath } from "@/components/CharacterLink";
import { apiBase } from "@/lib/api";
import { className, classColor, namespaceLabel } from "@/lib/game";
import type { CharacterSummary, SearchResponse } from "@/lib/types";

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

  return (
    <form role="search" onSubmit={submit} className="w-full">
      <div className={`flex items-stretch gap-2 ${compact ? "" : "flex-col sm:flex-row"}`}>
        <label className="sr-only" htmlFor={compact ? "search-compact" : "search-main"}>
          Character name
        </label>
        <div className="relative flex-1 min-w-0 flex">
          <input
            id={compact ? "search-compact" : "search-main"}
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
            placeholder={compact ? "Search characters…" : "Character name, e.g. Asha Brightvale"}
            maxLength={64}
            autoComplete="off"
            className={`flex-1 min-w-0 rounded-lg bg-surface-2 border border-line placeholder:text-faint focus-ring ${
              compact ? "h-9 px-3 text-sm" : "h-12 px-4 text-base"
            }`}
          />
          {showList && (
            <ul
              id={listId}
              role="listbox"
              aria-label="Matching characters"
              className={`card absolute top-full z-50 mt-1 py-1 overflow-hidden text-left shadow-xl shadow-black/40 ${
                compact ? "right-0 w-[min(22rem,calc(100vw-2rem))]" : "left-0 right-0"
              }`}
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
                  className={`px-3 py-2 cursor-pointer ${i === active ? "bg-surface-3" : ""}`}
                >
                  <div className="font-medium truncate" style={{ color: classColor(c.class_file) }}>
                    {c.full_name}
                  </div>
                  <div className="text-xs text-muted truncate">
                    {className(c.class_file)} · {namespaceLabel(c.namespace)} · {c.runs_observed} run{c.runs_observed === 1 ? "" : "s"}
                  </div>
                </li>
              ))}
              <li
                id={optionId(suggestions.length)}
                role="option"
                aria-selected={active === suggestions.length}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(suggestions.length)}
                onMouseEnter={() => setActive(suggestions.length)}
                className={`px-3 py-2 cursor-pointer text-sm text-gold border-t border-line ${
                  active === suggestions.length ? "bg-surface-3" : ""
                }`}
              >
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
            <select
              id="search-namespace"
              value={namespace}
              onChange={(e) => setNamespace(e.target.value)}
              className="h-12 rounded-lg bg-surface-2 border border-line px-3 text-sm focus-ring"
            >
              {NAMESPACES.map((n) => (
                <option key={n.value} value={n.value}>
                  {n.label}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="h-12 px-6 rounded-lg bg-gold text-ink font-semibold hover:bg-gold-strong focus-ring"
            >
              Search
            </button>
          </>
        )}
      </div>
      {error && !compact && (
        <p role="alert" className="mt-2 text-sm text-warn">
          {error}
        </p>
      )}
    </form>
  );
}
