"use client";

// Hand-rolled SVG/HTML charts: one series per chart (no legend needed, the title names it),
// thin marks, recessive grid, a crosshair tooltip, and a data table for every chart.
import { useEffect, useMemo, useRef, useState } from "react";

import { dateTime, dayShort, money, moneyCompact, pct, price, prob } from "@/lib/format";

// Formats are passed by name: server components can't hand functions to client components.
const VALUE_FORMATS = { money, moneyCompact, price, pct, prob } as const;
const TIME_FORMATS = { dayShort, dateTime } as const;
export type ValueFormat = keyof typeof VALUE_FORMATS;
export type TimeFormat = keyof typeof TIME_FORMATS;

function useWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

function niceTicks(min: number, max: number, count = 4) {
  const span = max - min || Math.abs(max) || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= count) ?? raw;
  const start = Math.ceil(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 1e-9; v += step) ticks.push(v);
  return ticks;
}

export type Point = { t: string; v: number };
export type RefLine = { value: number; label: string; tone: "buy" | "sell" | "neutral" };

export function LineChart({
  points,
  valueFormat,
  timeFormat = "dayShort",
  height = 220,
  refLines = [],
  label,
}: {
  points: Point[];
  valueFormat: ValueFormat;
  timeFormat?: TimeFormat;
  height?: number;
  refLines?: RefLine[];
  label: string;
}) {
  const formatValue = (v: number) => VALUE_FORMATS[valueFormat](v);
  const formatTime = (t: string) => TIME_FORMATS[timeFormat](t);
  const [box, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const innerH = height - 12 - 24;
  const { y, ticks, pad } = useMemo(() => {
    const values = [...points.map((p) => p.v), ...refLines.map((r) => r.value)];
    let lo = Math.min(...values);
    let hi = Math.max(...values);
    const margin = (hi - lo || Math.abs(hi) || 1) * 0.08;
    lo -= margin;
    hi += margin;
    const ticks = niceTicks(lo, hi);
    // Left margin sized to the widest tick label (mono, ~6.8px per character at 11px).
    const longest = Math.max(...ticks.map((t) => VALUE_FORMATS[valueFormat](t).length));
    const pad = { top: 12, right: 12, bottom: 24, left: Math.ceil(longest * 6.8) + 14 };
    return { y: (v: number) => pad.top + innerH - ((v - lo) / (hi - lo)) * innerH, ticks, pad };
  }, [points, refLines, innerH, valueFormat]);
  const innerW = width - pad.left - pad.right;

  if (points.length < 2) {
    return <p className="text-sm text-ink-3">Todavía no hay suficientes datos para graficar.</p>;
  }

  const x = (i: number) => pad.left + (i / (points.length - 1)) * innerW;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  const tone = { buy: "var(--buy)", sell: "var(--sell)", neutral: "var(--ink-3)" };

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left - pad.left;
    setHover(Math.max(0, Math.min(points.length - 1, Math.round((px / innerW) * (points.length - 1)))));
  }

  const h = hover != null ? points[hover] : null;
  return (
    <figure className="min-w-0">
      <div ref={box} className="relative w-full overflow-hidden">
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={label}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
          className="touch-none select-none"
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth="1" />
              <text x={pad.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="num" fontSize="11" fill="var(--ink-3)">
                {formatValue(t)}
              </text>
            </g>
          ))}
          {[...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])].map((i) => (
            <text key={i} x={x(i)} y={height - 6} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"} fontSize="11" fill="var(--ink-3)">
              {formatTime(points[i].t)}
            </text>
          ))}
          {refLines.map((r) => (
            <g key={r.label}>
              <line x1={pad.left} x2={width - pad.right} y1={y(r.value)} y2={y(r.value)} stroke={tone[r.tone]} strokeWidth="1.5" strokeDasharray="5 4" />
              <text x={width - pad.right} y={y(r.value) - 5} textAnchor="end" fontSize="11" fill="var(--ink-2)">
                {r.label} {formatValue(r.value)}
              </text>
            </g>
          ))}
          <path d={path} fill="none" stroke="var(--ink)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          {h && hover != null && (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + innerH} stroke="var(--ink-3)" strokeWidth="1" />
              <circle cx={x(hover)} cy={y(h.v)} r="4.5" fill="var(--ink)" stroke="var(--paper)" strokeWidth="2" />
            </g>
          )}
        </svg>
        {h && hover != null && (
          <div
            className="pointer-events-none absolute top-0 border border-rule bg-paper px-2 py-1 text-xs shadow-sm"
            style={{ left: Math.min(Math.max(x(hover) - 60, 0), width - 130) }}
          >
            <span className="text-ink-3">{formatTime(h.t)}</span> <span className="num text-ink">{formatValue(h.v)}</span>
          </div>
        )}
      </div>
      <details className="mt-1 text-xs text-ink-3">
        <summary className="cursor-pointer">Ver datos</summary>
        <table className="num mt-2 w-full max-w-sm">
          <tbody>
            {points.slice().reverse().map((p) => (
              <tr key={p.t} className="border-b border-rule">
                <td className="py-0.5">{formatTime(p.t)}</td>
                <td className="py-0.5 text-right text-ink">{formatValue(p.v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

// Treemap

export type TreemapItem = { id: string; label: string; sub: string; value: number; change: number; href?: string };
type Rect = { x: number; y: number; w: number; h: number; item: TreemapItem };

/** Squarified treemap layout (Bruls, Huizing, van Wijk). */
function squarify(items: TreemapItem[], x: number, y: number, w: number, h: number): Rect[] {
  const total = items.reduce((s, i) => s + i.value, 0);
  if (!total) return [];
  const scale = (w * h) / total;
  const nodes = items.map((item) => ({ item, area: item.value * scale })).sort((a, b) => b.area - a.area);
  const out: Rect[] = [];
  let row: typeof nodes = [];
  let rx = x, ry = y, rw = w, rh = h;
  const worst = (r: typeof nodes, side: number) => {
    const s = r.reduce((a, n) => a + n.area, 0);
    const max = Math.max(...r.map((n) => n.area));
    const min = Math.min(...r.map((n) => n.area));
    return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min));
  };
  const layoutRow = (r: typeof nodes) => {
    const s = r.reduce((a, n) => a + n.area, 0);
    if (rw >= rh) {
      const colW = s / rh;
      let cy = ry;
      for (const n of r) { const nh = n.area / colW; out.push({ x: rx, y: cy, w: colW, h: nh, item: n.item }); cy += nh; }
      rx += colW; rw -= colW;
    } else {
      const rowH = s / rw;
      let cx = rx;
      for (const n of r) { const nw = n.area / rowH; out.push({ x: cx, y: ry, w: nw, h: rowH, item: n.item }); cx += nw; }
      ry += rowH; rh -= rowH;
    }
  };
  for (const n of nodes) {
    const side = Math.min(rw, rh);
    if (row.length === 0 || worst([...row, n], side) <= worst(row, side)) row.push(n);
    else { layoutRow(row); row = [n]; }
  }
  if (row.length) layoutRow(row);
  return out;
}

/** Diverging fill for a % change: sell color below zero, buy color above, paper at zero. */
function changeFill(change: number, cap = 30) {
  const t = Math.max(-1, Math.min(1, change / cap));
  const pole = t >= 0 ? "var(--buy)" : "var(--sell)";
  return `color-mix(in oklab, ${pole} ${Math.round(Math.abs(t) * 55)}%, var(--paper-3))`;
}

export function Treemap({ items, height = 320, valueFormat = "money" }: { items: TreemapItem[]; height?: number; valueFormat?: ValueFormat }) {
  const formatValue = (v: number) => VALUE_FORMATS[valueFormat](v);
  const [box, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<string | null>(null);
  const rects = useMemo(() => squarify(items.filter((i) => i.value > 0), 0, 0, width, height), [items, width, height]);
  const total = items.reduce((s, i) => s + i.value, 0);
  const gap = 2;
  return (
    <figure className="min-w-0">
      <div ref={box} className="relative w-full overflow-hidden" style={{ height }} role="img" aria-label="Composición de la cartera por valor">
        {rects.map(({ x, y, w, h, item }) => {
          const share = item.value / total;
          const roomy = w > 70 && h > 44;
          const Tag = item.href ? "a" : "div";
          return (
            <Tag
              key={item.id}
              href={item.href}
              onPointerEnter={() => setHover(item.id)}
              onPointerLeave={() => setHover(null)}
              className="absolute overflow-hidden px-2 py-1.5 transition-[filter] hover:brightness-95"
              style={{
                left: x + gap / 2, top: y + gap / 2, width: Math.max(w - gap, 0), height: Math.max(h - gap, 0),
                background: changeFill(item.change), borderRadius: 3,
                outline: hover === item.id ? "2px solid var(--ink)" : "none",
              }}
            >
              {w > 36 && h > 20 && <p className="font-mono text-xs font-medium text-ink">{item.label}</p>}
              {roomy && <p className="num text-[0.7rem] text-ink-2">{(share * 100).toFixed(0)}% | {item.change > 0 ? "+" : ""}{item.change.toFixed(1)}%</p>}
            </Tag>
          );
        })}
        {hover && (() => {
          const r = rects.find((q) => q.item.id === hover);
          if (!r) return null;
          return (
            <div className="pointer-events-none absolute z-10 border border-rule bg-paper px-2 py-1 text-xs shadow-sm"
              style={{ left: Math.min(r.x + 8, width - 220), top: Math.min(r.y + r.h - 8, height - 50) }}>
              <p className="font-medium text-ink">{r.item.label} <span className="text-ink-3">{r.item.sub}</span></p>
              <p className="num text-ink-2">{formatValue(r.item.value)} ({((r.item.value / total) * 100).toFixed(1)}% de la cartera) | {r.item.change > 0 ? "+" : ""}{r.item.change.toFixed(1)}% de ganancia</p>
            </div>
          );
        })()}
      </div>
      <figcaption className="mt-2 flex items-center gap-2 text-xs text-ink-3">
        <span>Ganancia: -30%</span>
        <span className="h-2 w-40 rounded-sm" style={{ background: `linear-gradient(90deg, ${changeFill(-30)}, var(--paper-3), ${changeFill(30)})` }} />
        <span>+30%</span>
        <span className="ml-2">El tamaño es el valor de cada posición.</span>
      </figcaption>
    </figure>
  );
}
