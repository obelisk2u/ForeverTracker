import { ChevronRight } from "lucide-react";

import { ClassDot } from "@/components/Badges";
import { ItemTooltip } from "@/components/ItemTooltip";
import { classColor } from "@/lib/game";
import { isHidden, type Participant, type TooltipLine } from "@/lib/types";

// The game's item quality colours (poor, common, uncommon, rare, epic, legendary, artifact, heirloom).
const QUALITY = ["#9d9d9d", "#ffffff", "#1eff00", "#0070dd", "#a335ee", "#ff8000", "#e6cc80", "#00ccff"];

function itemName(link: string | null | undefined, itemId: number): string {
  const m = link?.match(/\[(.+?)\]/);
  return m ? m[1] : `Item ${itemId}`;
}

type GearItem = NonNullable<Participant["gear"]>["items"][number];

// The tooltip the game showed for this item, as an addon user's game read it; until one has been
// recorded, its name, item level and slot.
function tooltipFor(item: GearItem): { lines: TooltipLine[]; note?: string } {
  if (item.tooltip?.length) return { lines: item.tooltip };
  const lines: TooltipLine[] = [{ left: itemName(item.link, item.item_id), color: (QUALITY[item.quality ?? 1] ?? QUALITY[1]).slice(1) }];
  if (item.item_level) lines.push({ left: `Item Level ${item.item_level}`, color: "ffd100" });
  lines.push({ left: item.slot_name });
  return { lines, note: "The full tooltip appears once a ForeverTracker user sees this item in game." };
}

// What each party member wore in this run, one collapsible card per person.
export function RunGear({ participants }: { participants: Participant[] }) {
  const visible = participants.filter((p) => !isHidden(p.character));
  if (!visible.some((p) => p.gear)) {
    return <p className="text-sm text-muted-foreground">Nobody&apos;s gear was seen during this run.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {visible.map((p, i) => {
        const name = isHidden(p.character) ? "" : p.character.full_name;
        const heading = (
          <span className="flex min-w-0 items-center gap-2">
            <ClassDot classFile={p.class_file} />
            <span className="truncate font-medium" style={{ color: classColor(p.class_file) }}>
              {name}
            </span>
          </span>
        );
        if (!p.gear) {
          return (
            <div key={i} className="flex items-center justify-between gap-3 rounded-lg border border-dashed px-4 py-2.5 text-sm">
              {heading}
              <span className="text-faint">Gear not seen</span>
            </div>
          );
        }
        const ilvl = p.gear.average_item_level;
        return (
          <details key={i} className="group rounded-lg border bg-card text-sm">
            <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-4 py-2.5 hover:bg-accent/40 [&::-webkit-details-marker]:hidden">
              {heading}
              <span className="flex shrink-0 items-center gap-3 text-muted-foreground">
                {ilvl !== null && ilvl !== undefined && (
                  <span>
                    ilvl <span className="text-foreground tabular">{ilvl.toFixed(1)}</span>
                  </span>
                )}
                <span className="text-faint">{p.gear.items.length} items</span>
                <ChevronRight aria-hidden="true" className="size-4 text-faint transition-transform group-open:rotate-90" />
              </span>
            </summary>
            <ul className="mx-4 mb-3 border-t pt-2">
              {p.gear.items.map((item) => {
                const tip = tooltipFor(item);
                return (
                  <li key={item.slot}>
                    <ItemTooltip lines={tip.lines} note={tip.note}>
                      <button
                        type="button"
                        className="focus-ring -mx-2 flex w-[calc(100%+1rem)] cursor-default items-baseline justify-between gap-3 rounded px-2 py-1 text-left hover:bg-accent/50"
                      >
                        <span className="w-24 shrink-0 text-xs text-faint">{item.slot_name}</span>
                        <span className="flex-1 truncate" style={{ color: QUALITY[item.quality ?? 1] ?? QUALITY[1] }}>
                          {itemName(item.link, item.item_id)}
                        </span>
                        <span className="text-xs text-muted-foreground tabular">{item.item_level ?? "—"}</span>
                      </button>
                    </ItemTooltip>
                  </li>
                );
              })}
            </ul>
          </details>
        );
      })}
    </div>
  );
}
