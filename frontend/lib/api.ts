import type {
  ActivityItem,
  CharacterProfile,
  MetaOut,
  OverviewStats,
  RunDetail,
  RunHistoryResponse,
  SearchResponse,
  UploaderRelease,
} from "./types";

// Server components reach the API over the internal network; the browser uses the public URL.
export function apiBase(): string {
  if (typeof window === "undefined") {
    return process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(path: string, revalidate = 30): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, { next: { revalidate } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

const enc = encodeURIComponent;

export const api = {
  meta: () => get<MetaOut>("/api/v1/meta", 15),
  overview: () => get<OverviewStats>("/api/v1/stats/overview", 60),
  recent: (limit = 12) => get<ActivityItem[]>(`/api/v1/activity/recent${qs({ limit })}`),
  dungeons: () => get<Array<{ slug: string; name: string; runs: number }>>("/api/v1/dungeons", 300),
  search: (q: string, opts: { namespace?: string; class?: string; exact?: boolean; page?: number } = {}) =>
    get<SearchResponse>(`/api/v1/search${qs({ q, ...opts })}`),
  character: (ns: string, id: string) => get<CharacterProfile>(`/api/v1/characters/${enc(ns)}/${enc(id)}`),
  runs: (ns: string, id: string, opts: { page?: number; dungeon?: string; role?: string; outcome?: string } = {}) =>
    get<RunHistoryResponse>(`/api/v1/characters/${enc(ns)}/${enc(id)}/runs${qs(opts)}`),
  run: (id: string) => get<RunDetail>(`/api/v1/runs/${enc(id)}`),
  uploaderRelease: () => get<UploaderRelease>("/api/v1/uploader/latest", 300),
};
