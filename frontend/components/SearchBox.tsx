"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

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
  const [query, setQuery] = useState(initialQuery);
  const [namespace, setNamespace] = useState(initialNamespace);
  const [error, setError] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (q.length < 2) {
      setError("Type at least 2 characters of a character name.");
      return;
    }
    setError(null);
    const params = new URLSearchParams({ q });
    if (namespace) params.set("namespace", namespace);
    router.push(`/search?${params.toString()}`);
  }

  return (
    <form role="search" onSubmit={submit} className="w-full">
      <div className={`flex items-stretch gap-2 ${compact ? "" : "flex-col sm:flex-row"}`}>
        <label className="sr-only" htmlFor={compact ? "search-compact" : "search-main"}>
          Character name
        </label>
        <input
          id={compact ? "search-compact" : "search-main"}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={compact ? "Search characters…" : "Character name, e.g. Asha Brightvale"}
          maxLength={64}
          autoComplete="off"
          className={`flex-1 min-w-0 rounded-lg bg-surface-2 border border-line placeholder:text-faint focus-ring ${
            compact ? "h-9 px-3 text-sm" : "h-12 px-4 text-base"
          }`}
        />
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
