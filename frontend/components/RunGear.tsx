import { ItemTooltip, type TooltipLine } from "@/components/ItemTooltip";
import { classColor, qualityColor } from "@/lib/game";
import { isHidden, type GearItem, type Participant } from "@/lib/types";

function itemName(link: string | null | undefined, itemId: number): string {
  const m = link?.match(/\[(.+?)\]/);
  return m ? m[1] : `Item ${itemId}`;
}

// The game's tooltip as the addon recorded it; for items recorded before that (or before the game
// had loaded them), what is known: name, item level and slot.
export function itemTooltip(item: GearItem): TooltipLine[] {
  if (item.tooltip && item.tooltip.length > 0) return item.tooltip;
  const lines: TooltipLine[] = [{ left: itemName(item.link, item.item_id), color: qualityColor(item.quality).slice(1) }];
  if (item.item_level !== null && item.item_level !== undefined) lines.push({ left: `Item Level ${item.item_level}`, color: "ffd100" });
  lines.push({ left: item.slot_name });
  lines.push({ left: "The item's stats were not recorded.", color: "808080" });
  return lines;
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
                  <span className="flex-1 min-w-0">
                    <ItemTooltip lines={itemTooltip(item)} className="inline-block max-w-full truncate align-bottom" style={{ color: qualityColor(item.quality) }}>
                      {itemName(item.link, item.item_id)}
                    </ItemTooltip>
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
