"use client";

// A single-series line chart with a hover tooltip, optional dashed reference lines, and optional
// marks: a thin bar at a point showing how much of that day's jump was money moved in or out.
// Marks carry no text on the plot; their label shows in the tooltip (and callers list them below).
import { useEffect, useMemo, useRef, useState } from "react";

import { dateTime, dayShort, money, moneyCompact, price } from "@/lib/format";

// Formats are passed by name: server components can't hand functions to client components.
const VALUE_FORMATS = { money, moneyCompact, price } as const;
const TIME_FORMATS = { dayShort, dateTime } as const;
export type ValueFormat = keyof typeof VALUE_FORMATS;
export type TimeFormat = keyof typeof TIME_FORMATS;

export type Point = { t: string; v: number };
export type RefLine = { value: number; label: string; tone: "buy" | "sell" };
/** At point i, the value moved by `delta` that isn't a gain or loss (a deposit or withdrawal). */
export type Mark = { i: number; delta: number; label: string };

const MONTH = new Intl.DateTimeFormat("es-AR", { month: "short", timeZone: "America/Argentina/Buenos_Aires" });
const monthKey = (t: string) => new Date(t).toLocaleDateString("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }).slice(0, 7);

function niceTicks(min: number, max: number, count = 4) {
  const span = max - min || Math.abs(max) || 1;
  const mag = 10 ** Math.floor(Math.log10(span / count));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= count) ?? span / count;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) ticks.push(v);
  return ticks;
}

export function LineChart({
  points,
  valueFormat,
  timeFormat = "dayShort",
  height = 240,
  refLines = [],
  marks = [],
  label,
}: {
  points: Point[];
  valueFormat: ValueFormat;
  timeFormat?: TimeFormat;
  height?: number;
  refLines?: RefLine[];
  marks?: Mark[];
  label: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.floor(e.contentRect.width))));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const fmt = (v: number) => VALUE_FORMATS[valueFormat](v);
  // The tooltip shows the exact value, so it matches the same number anywhere else on the page.
  const fmtExact = (v: number) => (valueFormat === "moneyCompact" ? money(v) : fmt(v));
  const fmtTime = (t: string) => TIME_FORMATS[timeFormat](t);
  const innerH = height - 12 - 24;

  const { y, ticks, left } = useMemo(() => {
    const ends = marks.filter((m) => points[m.i]).map((m) => points[m.i].v - m.delta);
    const values = [...points.map((p) => p.v), ...refLines.map((r) => r.value), ...ends];
    let lo = Math.min(...values);
    let hi = Math.max(...values);
    const margin = (hi - lo || Math.abs(hi) || 1) * 0.08;
    lo -= margin;
    hi += margin;
    const ticks = niceTicks(lo, hi);
    const left = Math.ceil(Math.max(...ticks.map((t) => VALUE_FORMATS[valueFormat](t).length)) * 6.6) + 12;
    return { y: (v: number) => 12 + innerH - ((v - lo) / (hi - lo)) * innerH, ticks, left };
  }, [points, refLines, marks, innerH, valueFormat]);

  if (points.length < 2) return <p className="text-text-2">Todavía no hay datos suficientes para el gráfico.</p>;

  const right = 12;
  const innerW = width - left - right;
  const x = (i: number) => left + (i / (points.length - 1)) * innerW;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  const floor = 12 + innerH;
  const area = `${path}L${x(points.length - 1).toFixed(1)},${floor}L${x(0).toFixed(1)},${floor}Z`;
  const h = hover != null ? points[hover] : null;
  const hMark = hover != null ? marks.find((m) => m.i === hover) : undefined;
  const shown = marks.filter((m) => points[m.i]);
  // Time axis: the first day of each month when the span is long, else the two ends.
  const monthStarts = points.flatMap((p, i) => (i > 0 && monthKey(p.t) !== monthKey(points[i - 1].t) ? [i] : []));
  const xTicks = points.length > 40 && monthStarts.length >= 2
    ? monthStarts.map((i) => ({ i, text: MONTH.format(new Date(points[i].t)).replace(".", ""), anchor: "middle" as const }))
    : [...new Set([0, points.length - 1])].map((i) => ({ i, text: fmtTime(points[i].t), anchor: i === 0 ? ("start" as const) : ("end" as const) }));

  return (
    <div ref={box} className="relative w-full min-w-0 overflow-hidden">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={label}
        className="touch-none select-none"
        onPointerLeave={() => setHover(null)}
        onPointerMove={(e) => {
          const px = e.clientX - e.currentTarget.getBoundingClientRect().left;
          let i = Math.max(0, Math.min(points.length - 1, Math.round(((px - left) / innerW) * (points.length - 1))));
          // A mark within 8px is easier to hit than the exact day.
          const near = shown.find((m) => Math.abs(x(m.i) - px) <= 8);
          if (near) i = near.i;
          setHover(i);
        }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
            <text x={left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize="11" fill="var(--text-3)" className="num">{fmt(t)}</text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t.i} x={x(t.i)} y={height - 6} textAnchor={t.anchor} fontSize="11" fill="var(--text-3)">{t.text}</text>
        ))}
        {refLines.map((r) => (
          <g key={r.label}>
            <line x1={left} x2={width - right} y1={y(r.value)} y2={y(r.value)} stroke={`var(--${r.tone})`} strokeWidth="1.5" strokeDasharray="5 4" />
            <text x={width - right} y={y(r.value) - 6} textAnchor="end" fontSize="11" fill="var(--text-2)">{r.label}</text>
          </g>
        ))}
        <path d={area} fill="var(--text)" fillOpacity="0.05" stroke="none" />
        {h && hover != null && <line x1={x(hover)} x2={x(hover)} y1={12} y2={floor} stroke="var(--border)" />}
        {shown.map((m) => {
          // The part of the day's jump that was money in or out: from the value before to after.
          const y1 = y(points[m.i].v - m.delta);
          const y2 = y(points[m.i].v);
          return (
            <rect
              key={`${m.i}-${m.label}`}
              x={x(m.i) - 2}
              y={Math.min(y1, y2)}
              width="4"
              height={Math.max(3, Math.abs(y2 - y1))}
              rx="2"
              fill="var(--text-3)"
              fillOpacity={hover === m.i ? 1 : 0.7}
            />
          );
        })}
        <path d={path} fill="none" stroke="var(--text)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {shown.map((m) => (
          <circle key={`dot-${m.i}`} cx={x(m.i)} cy={y(points[m.i].v)} r="4" fill="var(--bg)" stroke="var(--text-2)" strokeWidth="2" />
        ))}
        {h && hover != null && (
          <circle cx={x(hover)} cy={y(h.v)} r="4.5" fill="var(--text)" stroke="var(--bg)" strokeWidth="2" />
        )}
      </svg>
      {h && hover != null && (
        <div
          className="pointer-events-none absolute top-0 rounded-md border border-border bg-bg px-2 py-1 text-xs shadow-sm"
          style={{ left: Math.min(Math.max(x(hover) - 70, 0), width - (hMark ? 200 : 150)) }}
        >
          <p><span className="num font-medium">{fmtExact(h.v)}</span> <span className="text-text-3">{fmtTime(h.t)}</span></p>
          {hMark && <p className="num text-text-2">{hMark.label}</p>}
        </div>
      )}
    </div>
  );
}
