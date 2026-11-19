const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const oneDp = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

export function formatAmount(v: number): string {
  return Math.abs(v) >= 10_000 ? compact.format(v) : whole.format(v);
}

export function formatRate(v: number): string {
  return v >= 1000 ? compact.format(v) : oneDp.format(v);
}

export function formatCount(v: number): string {
  return whole.format(v);
}

export function formatNumber(v: number, unit: string): string {
  if (unit === "per_second") return formatRate(v);
  if (unit === "count") return formatCount(v);
  return formatAmount(v);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m.toString().padStart(2, "0")}m`;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

// Dates are written in UTC on the server, which cannot know the viewer's timezone; LocalTime rewrites
// them in the browser's own zone (an IANA name such as "America/Chicago").
const DATE_STYLES = {
  absolute: { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short" },
  short: { month: "short", day: "numeric" },
  numeric: { month: "numeric", day: "numeric", year: "2-digit" },
} satisfies Record<string, Intl.DateTimeFormatOptions>;

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatIn(style: keyof typeof DATE_STYLES, iso: string, timeZone: string): string {
  const key = `${style}|${timeZone}`;
  let f = formatters.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", { ...DATE_STYLES[style], timeZone });
    formatters.set(key, f);
  }
  return f.format(new Date(iso));
}

export function formatDateTime(iso: string, timeZone = "UTC"): string {
  return formatIn("absolute", iso, timeZone);
}

export function formatShortDate(iso: string, timeZone = "UTC"): string {
  return formatIn("short", iso, timeZone);
}

export function formatNumericDate(iso: string, timeZone = "UTC"): string {
  return formatIn("numeric", iso, timeZone);
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const diff = (now.getTime() - new Date(iso).getTime()) / 1000;
  if (diff < 0) return "just now";
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  const days = Math.floor(diff / 86400);
  if (days < 60) return `${days} day${days === 1 ? "" : "s"} ago`;
  const months = Math.floor(days / 30);
  if (months < 24) return `${months} months ago`;
  return `${Math.floor(days / 365)} years ago`;
}

export function percent(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${oneDp.format(v)}%`;
}

// Time since the start of a run, like a stopwatch: "+4:07", "+1:02:09".
export function formatOffset(fromIso: string, toIso: string): string {
  const total = Math.max(0, Math.round((Date.parse(toIso) - Date.parse(fromIso)) / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = s.toString().padStart(2, "0");
  return h > 0 ? `+${h}:${m.toString().padStart(2, "0")}:${ss}` : `+${m}:${ss}`;
}
