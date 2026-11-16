"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { ITEM_QUALITY_COLOR } from "@/lib/game";

export interface TooltipLine {
  left: string;
  color?: string | null;
  right?: string | null;
  right_color?: string | null;
}

export interface Segment {
  text: string;
  color?: string;
}

// The game's text escapes: |cAARRGGBB ... |r and |cnIQ3: ... |r colour text, |T...|t and |A...|a
// are icons, |H...|h wraps a link, |n is a line break and || a literal bar.
const ESCAPE = /\|c([0-9a-fA-F]{8})|\|cn([A-Za-z0-9_]+):|\|r|\|T[^|]*\|t|\|A[^|]*\|a|\|H[^|]*\|h|\|h|\|n|\|\|/g;

export function tooltipSegments(text: string, color?: string): Segment[] {
  const out: Segment[] = [];
  const colors: (string | undefined)[] = [color];
  const current = () => colors[colors.length - 1];
  const push = (t: string) => {
    if (t) out.push({ text: t, color: current() });
  };
  let last = 0;
  for (const m of text.matchAll(ESCAPE)) {
    push(text.slice(last, m.index));
    last = m.index + m[0].length;
    if (m[1]) colors.push(`#${m[1].slice(2)}`);
    else if (m[2]) {
      const quality = /^IQ(\d+)$/.exec(m[2]);
      colors.push(quality ? ITEM_QUALITY_COLOR[Number(quality[1])] ?? current() : current());
    } else if (m[0] === "|r") {
      if (colors.length > 1) colors.pop();
    } else if (m[0] === "|n") push("\n");
    else if (m[0] === "||") push("|");
  }
  push(text.slice(last));
  return out;
}

function hex(color: string | null | undefined): string {
  return color ? `#${color}` : "#ffffff";
}

function Text({ text, color }: { text: string; color?: string | null }) {
  return (
    <>
      {tooltipSegments(text, hex(color)).map((s, i) => (
        <span key={i} style={{ color: s.color }}>
          {s.text}
        </span>
      ))}
    </>
  );
}

// A tooltip drawn like the game's: dark panel, the item name in its quality colour, then each line
// with its own colour and an optional right-aligned part ("Head ... Plate").
export function TooltipPanel({ lines }: { lines: TooltipLine[] }) {
  return (
    <div className="flex flex-col">
      {lines.map((line, i) => (
        <div key={i} className={`flex justify-between gap-6 ${i === 0 ? "text-[15px] mb-0.5" : ""}`}>
          <span className="whitespace-pre-wrap">{line.left ? <Text text={line.left} color={line.color} /> : " "}</span>
          {line.right && (
            <span className="shrink-0 text-right">
              <Text text={line.right} color={line.right_color} />
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

const GAP = 8;

// Shows `lines` next to its children on hover, keyboard focus or a tap, kept inside the window.
export function ItemTooltip({
  lines,
  children,
  className,
  style,
}: {
  lines: TooltipLine[];
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const anchor = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();

  useLayoutEffect(() => {
    if (!open || !anchor.current || !panel.current) {
      setPos(null);
      return;
    }
    const a = anchor.current.getBoundingClientRect();
    const p = panel.current.getBoundingClientRect();
    // The visible area: innerWidth also counts anything wider than the screen.
    const width = document.documentElement.clientWidth;
    const height = document.documentElement.clientHeight;
    let left = a.right + GAP;
    let top = a.top;
    if (left + p.width > width - GAP) left = a.left - p.width - GAP;
    if (left < GAP) {
      left = Math.min(Math.max(GAP, a.left), width - p.width - GAP);
      top = a.bottom + GAP;
    }
    setPos({ left: Math.max(GAP, left), top: Math.max(GAP, Math.min(top, height - p.height - GAP)) });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const onPointer = (e: PointerEvent) => {
      if (!anchor.current?.contains(e.target as Node)) close();
    };
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  return (
    <>
      <button
        ref={anchor}
        type="button"
        aria-describedby={open ? id : undefined}
        className={`cursor-default text-left min-w-0 focus-ring rounded-sm ${className ?? ""}`}
        style={style}
        onPointerEnter={(e) => e.pointerType === "mouse" && setOpen(true)}
        onPointerLeave={(e) => e.pointerType === "mouse" && setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen(true)}
      >
        {children}
      </button>
      {open &&
        createPortal(
          <div
            ref={panel}
            id={id}
            role="tooltip"
            className="pointer-events-none fixed z-50 w-max max-w-[min(20rem,calc(100vw-1rem))] rounded-[5px] border border-[#6b6f7d] bg-[#070a12]/95 px-3 py-2 text-[13px] leading-[1.4] text-white shadow-[inset_0_0_0_1px_#1b1f2b,0_6px_18px_rgba(0,0,0,0.6)]"
            style={pos ? { left: pos.left, top: pos.top } : { left: -9999, top: -9999 }}
          >
            <TooltipPanel lines={lines} />
          </div>,
          document.body,
        )}
    </>
  );
}
