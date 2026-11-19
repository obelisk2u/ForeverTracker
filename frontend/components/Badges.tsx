import { Cross, Shield, Sword } from "lucide-react";

import { Badge as UiBadge } from "@/components/ui/badge";
import { OUTCOME, classColor, className, roleLabel } from "@/lib/game";
import { cn } from "@/lib/utils";

type Tone = "good" | "bad" | "warn" | "neutral" | "info" | "gold";

const TONES: Record<Tone, string> = {
  good: "border-success/25 bg-success/10 text-success",
  bad: "border-destructive/25 bg-destructive/10 text-destructive",
  warn: "border-warning/25 bg-warning/10 text-warning",
  neutral: "border-border bg-muted text-muted-foreground",
  info: "border-info/25 bg-info/10 text-info",
  gold: "border-primary/25 bg-primary/10 text-primary",
};

const DOTS: Record<Tone, string> = {
  good: "bg-success",
  bad: "bg-destructive",
  warn: "bg-warning",
  neutral: "bg-faint",
  info: "bg-info",
  gold: "bg-primary",
};

export function Badge({
  tone = "neutral",
  dot = false,
  children,
  title,
  className: extra,
}: {
  tone?: Tone;
  dot?: boolean;
  children: React.ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <UiBadge variant="outline" title={title} className={cn("rounded-md font-medium", TONES[tone], extra)}>
      {dot && <span aria-hidden="true" className={cn("size-1.5 rounded-full", DOTS[tone])} />}
      {children}
    </UiBadge>
  );
}

export function OutcomeBadge({ outcome, confidence }: { outcome: string; confidence: string }) {
  const info = OUTCOME[outcome] ?? OUTCOME.unknown;
  const title =
    outcome === "completed"
      ? confidence === "verified"
        ? "Completion confirmed by an in-game completion event"
        : "The final boss was killed (groups formed outside the dungeon finder get no completion event)"
      : outcome === "left" || outcome === "disconnected"
        ? "Observers left before any completion event; this does not mean the group failed"
        : undefined;
  return (
    <Badge tone={info.tone} title={title} dot>
      {info.label}
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

export function ClassDot({ classFile, className: extra }: { classFile: string | null | undefined; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block size-2 rounded-full shrink-0", extra)}
      style={{ backgroundColor: classColor(classFile) }}
    />
  );
}

const ROLE_ICONS = { TANK: Shield, HEALER: Cross, DAMAGER: Sword } as const;

// The group finder's three roles. Unknown roles get an empty slot so names stay aligned.
export function RoleIcon({ role, className: extra }: { role: string | null | undefined; className?: string }) {
  const Icon = role ? ROLE_ICONS[role as keyof typeof ROLE_ICONS] : undefined;
  const label = roleLabel(role);
  return (
    <span title={label} className={cn("inline-flex size-4 shrink-0 items-center justify-center text-faint", extra)}>
      {Icon ? <Icon className="size-3.5" strokeWidth={2.25} aria-hidden="true" /> : null}
      <span className="sr-only">{label}</span>
    </span>
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
