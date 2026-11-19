"use client";

import { Tooltip as TooltipPrimitive } from "radix-ui";
import { useState } from "react";

import type { TooltipLine } from "@/lib/types";

function hex(color: string | null | undefined): string {
  return color && /^[0-9a-f]{6}$/i.test(color) ? `#${color}` : "#ffffff";
}

// The game's tooltip, as the player saw it: a dark blue-black panel with a silver edge. Opens on
// hover, on keyboard focus, and on a tap (touch screens have no hover).
export function ItemTooltip({ lines, note, children }: { lines: TooltipLine[]; note?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <TooltipPrimitive.Provider delayDuration={0} skipDelayDuration={0} disableHoverableContent>
      <TooltipPrimitive.Root open={open} onOpenChange={setOpen}>
        <TooltipPrimitive.Trigger
          asChild
          onClick={(e) => {
            e.preventDefault(); // a click would otherwise close it
            setOpen(true);
          }}
        >
          {children}
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side="right"
            align="start"
            sideOffset={14}
            collisionPadding={12}
            className="z-50 w-max max-w-[min(19rem,calc(100vw-1.5rem))] min-w-[15rem] rounded-[6px] border border-[#6b6b80]/70 bg-[linear-gradient(180deg,rgb(16_16_38/0.97),rgb(5_5_16/0.97))] px-3 py-2.5 text-[12.5px] leading-[1.4] shadow-[0_0_0_1px_rgb(0_0_0/0.85),0_16px_40px_rgb(0_0_0/0.6)] data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0 data-[state=instant-open]:animate-in data-[state=instant-open]:fade-in-0"
          >
            {lines.map((l, i) => (
              <div key={i} className={i === 0 ? "mb-0.5 text-[14px] font-medium" : "flex justify-between gap-6"}>
                <span style={{ color: hex(l.color) }}>{l.left || " "}</span>
                {l.right && <span style={{ color: hex(l.right_color) }}>{l.right}</span>}
              </div>
            ))}
            {note && <div className="mt-2 border-t border-white/10 pt-1.5 text-[11px] text-[#8b8ba0] italic">{note}</div>}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
