import { OUTCOME, classColor, className } from "@/lib/game";

type Tone = "good" | "bad" | "warn" | "neutral" | "info" | "gold";

const TONES: Record<Tone, string> = {
  good: "bg-good/12 text-good border-good/30",
  bad: "bg-bad/12 text-bad border-bad/30",
  warn: "bg-warn/12 text-warn border-warn/30",
  neutral: "bg-surface-3 text-muted border-line-strong",
  info: "bg-info/12 text-info border-info/30",
  gold: "bg-gold/12 text-gold border-gold/30",
};

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: React.ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function OutcomeBadge({ outcome, confidence }: { outcome: string; confidence: string }) {
  const info = OUTCOME[outcome] ?? OUTCOME.unknown;
  const title =
    outcome === "completed"
      ? confidence === "verified"
        ? "Completion confirmed by an in-game completion event"
        : "Completion inferred from the final boss kill"
      : outcome === "left" || outcome === "disconnected"
        ? "Observers left before any completion event; this does not mean the group failed"
        : undefined;
  return (
    <Badge tone={info.tone} title={title}>
      {info.label}
      {outcome === "completed" && confidence === "probable" ? " (probable)" : ""}
    </Badge>
  );
}

export function ClassName({ classFile, children }: { classFile: string | null | undefined; children?: React.ReactNode }) {
  return (
    <span style={{ color: classColor(classFile) }} className="font-medium">
      {children ?? className(classFile)}
    </span>
  );
}

export function ClassDot({ classFile }: { classFile: string | null | undefined }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-2.5 w-2.5 rounded-full shrink-0"
      style={{ backgroundColor: classColor(classFile) }}
    />
  );
}

export function IdentityBadge({ confidence }: { confidence: string }) {
  return confidence === "guid_confirmed" ? (
    <Badge tone="good" title="Identified by the character's game GUID">
      GUID-confirmed
    </Badge>
  ) : (
    <Badge tone="warn" title="Identified by name only; may be less reliable">
      Name only
    </Badge>
  );
}
