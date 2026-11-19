"use client";

import { useSyncExternalStore } from "react";

import { formatDateTime, formatNumericDate, formatShortDate, relativeTime } from "@/lib/format";

const never = () => () => {};

// The viewer's timezone. The server renders in UTC; hydration then re-renders in the browser's zone,
// and pages opened by client-side navigation use the browser's zone from the start.
export function useTimeZone(): string {
  return useSyncExternalStore(
    never,
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    () => "UTC",
  );
}

const FORMATS = {
  datetime: formatDateTime,
  short: formatShortDate,
  numeric: formatNumericDate,
} as const;

// A <time> in the viewer's timezone, with the full date and time on hover. `children` replaces the
// visible text (a stopwatch offset, say) while keeping the local hover text.
export function LocalTime({
  iso,
  format = "datetime",
  now,
  className,
  children,
}: {
  iso: string;
  format?: keyof typeof FORMATS | "relative";
  now?: Date;
  className?: string;
  children?: React.ReactNode;
}) {
  const zone = useTimeZone();
  const text = children ?? (format === "relative" ? relativeTime(iso, now) : FORMATS[format](iso, zone));
  return (
    <time dateTime={iso} title={formatDateTime(iso, zone)} className={className}>
      {text}
    </time>
  );
}
