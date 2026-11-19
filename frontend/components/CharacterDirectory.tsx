"use client";

import { useState } from "react";

import { CharacterCard, CharacterTable } from "@/components/SearchResults";
import { Button } from "@/components/ui/button";
import { apiBase } from "@/lib/api";
import type { CharacterListResponse } from "@/lib/types";

// The first page comes from the server; "Show more" fetches the next one and adds it below.
export function CharacterDirectory({ initial }: { initial: CharacterListResponse }) {
  const [items, setItems] = useState(initial.results);
  const [page, setPage] = useState(initial.page);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  async function showMore() {
    setLoading(true);
    setFailed(false);
    try {
      const res = await fetch(`${apiBase()}/api/v1/characters?page=${page + 1}&page_size=${initial.page_size}`);
      if (!res.ok) throw new Error(res.statusText);
      const next = (await res.json()) as CharacterListResponse;
      // New runs can reorder the list between pages; never show anyone twice.
      setItems((current) => {
        const seen = new Set(current.map((c) => c.id));
        return [...current, ...next.results.filter((c) => !seen.has(c.id))];
      });
      setPage(next.page);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  const more = page * initial.page_size < initial.total;
  return (
    <div className="flex flex-col gap-4">
      <CharacterTable>
        <ul className="divide-y">
          {items.map((c) => (
            <li key={c.id}>
              <CharacterCard c={c} />
            </li>
          ))}
        </ul>
      </CharacterTable>
      <div className="flex flex-wrap items-center gap-4">
        {more && (
          <Button type="button" variant="outline" size="lg" onClick={showMore} disabled={loading} className="px-4">
            {loading ? "Loading…" : "Show more"}
          </Button>
        )}
        <span className="text-sm text-faint">
          Showing {items.length.toLocaleString("en-US")} of {initial.total.toLocaleString("en-US")}
        </span>
        {failed && (
          <span role="alert" className="text-sm text-warning">
            Couldn&apos;t load more characters. Try again.
          </span>
        )}
      </div>
    </div>
  );
}
