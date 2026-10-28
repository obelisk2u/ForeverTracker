import { Freshness } from "@/components/Freshness";
import type { GearSnapshot } from "@/lib/types";

const QUALITY = ["#9d9d9d", "#ffffff", "#1eff00", "#0070dd", "#a335ee", "#ff8000", "#e6cc80", "#00ccff"];

function itemName(link: string | null | undefined, itemId: number): string {
  const m = link?.match(/\[(.+?)\]/);
  return m ? m[1] : `Item ${itemId}`;
}

export function GearList({ gear }: { gear: GearSnapshot | null }) {
  if (!gear) {
    return <p className="text-sm text-muted">No equipment has been observed for this character yet.</p>;
  }
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <span className="text-sm text-muted">
          {gear.average_item_level !== null && gear.average_item_level !== undefined ? (
            <>
              Average item level <strong className="text-text tabular">{gear.average_item_level.toFixed(1)}</strong>
            </>
          ) : (
            "Average item level unavailable"
          )}
          {" · "}
          {gear.source === "inspect" ? "seen by inspection" : "reported by the character's own addon"}
          {gear.status === "partial" && " · partial"}
        </span>
        <Freshness iso={gear.observed_at} label="Observed" />
      </div>
      <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
        {gear.items.map((item) => (
          <li key={item.slot} className="flex items-baseline justify-between gap-3 border-b border-line/40 py-1">
            <span className="text-faint w-20 shrink-0">{item.slot_name}</span>
            <span className="truncate flex-1" style={{ color: QUALITY[item.quality ?? 1] ?? QUALITY[1] }}>
              {itemName(item.link, item.item_id)}
            </span>
            <span className="tabular text-muted">{item.item_level ?? "—"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
