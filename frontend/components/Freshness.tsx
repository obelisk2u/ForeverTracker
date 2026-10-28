import { formatDateTime, relativeTime } from "@/lib/format";

export function Freshness({ iso, label = "Last observed", now }: { iso: string; label?: string; now?: Date }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-muted">
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-good" />
      {label}{" "}
      <time dateTime={iso} title={formatDateTime(iso)} className="text-text">
        {relativeTime(iso, now)}
      </time>
    </span>
  );
}

export function Timestamp({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} title={formatDateTime(iso)}>
      {formatDateTime(iso)}
    </time>
  );
}
