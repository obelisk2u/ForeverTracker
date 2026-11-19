import { LocalTime } from "@/components/LocalTime";

export function Freshness({ iso, label = "Last observed", now }: { iso: string; label?: string; now?: Date }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
      <span aria-hidden="true" className="relative flex size-2">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-40 motion-reduce:hidden" />
        <span className="relative inline-flex size-2 rounded-full bg-success" />
      </span>
      {label}{" "}
      <LocalTime iso={iso} format="relative" now={now} className="text-foreground" />
    </span>
  );
}

export function Timestamp({ iso }: { iso: string }) {
  return (
    <LocalTime iso={iso} />
  );
}
