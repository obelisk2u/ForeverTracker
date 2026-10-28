import type { Metadata } from "next";

import { SearchBox } from "@/components/SearchBox";
import { SearchResults } from "@/components/SearchResults";
import { Notice, Pagination } from "@/components/States";
import { ApiError, api } from "@/lib/api";
import { CLASS_INFO } from "@/lib/game";
import type { SearchResponse } from "@/lib/types";

export const metadata: Metadata = { title: "Search" };
export const dynamic = "force-dynamic";

type Params = { q?: string; namespace?: string; class?: string; exact?: string; page?: string };

export default async function SearchPage({ searchParams }: { searchParams: Promise<Params> }) {
  const sp = await searchParams;
  const q = (sp.q ?? "").trim();
  const page = Math.max(1, Number(sp.page ?? 1) || 1);
  let data: SearchResponse | null = null;
  let error: string | null = null;
  if (q.length >= 2) {
    try {
      data = await api.search(q, { namespace: sp.namespace, class: sp.class, exact: sp.exact === "true", page });
    } catch (e) {
      error = e instanceof ApiError && e.status === 422 ? "Type at least 2 characters." : "Search is unavailable right now.";
    }
  }
  const base = new URLSearchParams();
  if (q) base.set("q", q);
  if (sp.namespace) base.set("namespace", sp.namespace);
  if (sp.class) base.set("class", sp.class);
  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-3xl">Find a character</h1>
      <SearchBox initialQuery={q} initialNamespace={sp.namespace ?? ""} />
      <form className="flex flex-wrap items-center gap-3 text-sm" action="/search">
        <input type="hidden" name="q" value={q} />
        {sp.namespace && <input type="hidden" name="namespace" value={sp.namespace} />}
        <label className="flex items-center gap-2">
          <span className="text-muted">Class</span>
          <select name="class" defaultValue={sp.class ?? ""} className="h-9 rounded-md bg-surface-2 border border-line px-2">
            <option value="">Any</option>
            {Object.entries(CLASS_INFO).map(([k, v]) => (
              <option key={k} value={k}>
                {v.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" name="exact" value="true" defaultChecked={sp.exact === "true"} />
          <span className="text-muted">Exact name</span>
        </label>
        <button type="submit" className="h-9 px-3 rounded-md border border-line hover:bg-surface-2">
          Apply
        </button>
      </form>
      {error && <Notice tone="warn">{error}</Notice>}
      {data && <SearchResults data={data} />}
      {data && (
        <Pagination
          page={page}
          pageSize={data.page_size}
          total={data.total}
          href={(p) => {
            const params = new URLSearchParams(base);
            if (sp.exact) params.set("exact", sp.exact);
            params.set("page", String(p));
            return `/search?${params.toString()}`;
          }}
        />
      )}
      {!q && <p className="text-muted text-sm">Enter part of a character name. Forever names have two parts, for example “Asha Brightvale”.</p>}
    </div>
  );
}
