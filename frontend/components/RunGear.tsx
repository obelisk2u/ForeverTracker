import { classColor } from "@/lib/game";
import { isHidden, type Participant } from "@/lib/types";

// The game's item quality colours (poor, common, uncommon, rare, epic, legendary, artifact, heirloom).
const QUALITY = ["#9d9d9d", "#ffffff", "#1eff00", "#0070dd", "#a335ee", "#ff8000", "#e6cc80", "#00ccff"];

function itemName(link: string | null | undefined, itemId: number): string {
  const m = link?.match(/\[(.+?)\]/);
  return m ? m[1] : `Item ${itemId}`;
}

// What each party member wore in this run, one collapsible card per person.
export function RunGear({ participants }: { participants: Participant[] }) {
  const visible = participants.filter((p) => !isHidden(p.character));
  if (!visible.some((p) => p.gear)) {
    return <p className="text-sm text-muted">Nobody&apos;s gear was seen during this run.</p>;
  }
  return (
    <div className="grid lg:grid-cols-2 gap-3 items-start">
      {visible.map((p, i) => {
        const name = isHidden(p.character) ? "" : p.character.full_name;
        const heading = (
          <span className="font-medium truncate" style={{ color: classColor(p.class_file) }}>
            {name}
          </span>
        );
        if (!p.gear) {
          return (
            <div key={i} className="card px-4 py-3 flex items-center justify-between gap-3">
              {heading}
              <span className="text-sm text-faint">Gear not seen</span>
            </div>
          );
        }
        const ilvl = p.gear.average_item_level;
        return (
          <details key={i} className="card px-4 py-3 group">
            <summary className="cursor-pointer list-none flex items-center justify-between gap-3 focus-ring rounded">
              {heading}
              <span className="text-sm text-muted shrink-0">
                {ilvl !== null && ilvl !== undefined && (
                  <>
                    Item level <span className="text-text tabular">{ilvl.toFixed(1)}</span> ·{" "}
                  </>
                )}
                {p.gear.items.length} items <span className="inline-block text-faint transition-transform group-open:rotate-90">›</span>
              </span>
            </summary>
            <ul className="mt-3 text-sm">
              {p.gear.items.map((item) => (
                <li key={item.slot} className="flex items-baseline justify-between gap-3 border-t border-line/40 py-1">
                  <span className="text-faint w-20 shrink-0">{item.slot_name}</span>
                  <span className="truncate flex-1" style={{ color: QUALITY[item.quality ?? 1] ?? QUALITY[1] }}>
                    {itemName(item.link, item.item_id)}
                  </span>
                  <span className="tabular text-muted">{item.item_level ?? "—"}</span>
                </li>
              ))}
            </ul>
          </details>
        );
      })}
    </div>
  );
}
