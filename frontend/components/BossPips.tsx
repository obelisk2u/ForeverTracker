import type { EncounterOut } from "@/lib/types";
import { cn } from "@/lib/utils";

function state(e: EncounterOut): { label: string; cls: string } {
  if (e.conflict) return { label: "observers disagree", cls: "border-warning bg-transparent" };
  if (e.success === true) return { label: "killed", cls: "border-primary bg-primary" };
  if (e.success === false) return { label: "wipe", cls: "border-destructive bg-transparent" };
  return { label: "outcome unknown", cls: "border-faint bg-transparent" };
}

// One small diamond per boss pull, in pull order: filled for a kill, a red outline for a wipe.
export function BossPips({ encounters, className }: { encounters: EncounterOut[]; className?: string }) {
  if (encounters.length === 0) return null;
  const kills = encounters.filter((e) => e.success === true).length;
  const wipes = encounters.filter((e) => e.success === false).length;
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="inline-flex items-center gap-1.5" aria-hidden="true">
        {encounters.map((e, i) => {
          const s = state(e);
          return <span key={i} title={`${e.name ?? `Encounter ${e.encounter_id}`}: ${s.label}`} className={cn("size-2 rotate-45 rounded-[1px] border", s.cls)} />;
        })}
      </span>
      <span className="text-xs text-muted-foreground">
        {kills} boss{kills === 1 ? "" : "es"} killed
        {wipes > 0 && (
          <>
            {" "}
            · <span className="text-destructive">{wipes} wipe{wipes === 1 ? "" : "s"}</span>
          </>
        )}
      </span>
    </span>
  );
}
