"use client";

// A single-series line chart with a hover tooltip, optional dashed reference lines, and optional
// marks: a vertical bar at a point showing how much of that day's jump was money moved in or out.
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

/** Row (0, 1, 2) for each mark's label so labels closer than LABEL_W apart don't overlap. */
const LABEL_W = 120;
function placeLabels(marks: Mark[], xOf: (m: Mark) => number) {
  const lastX: number[] = [];
  return [...marks].sort((a, b) => xOf(a) - xOf(b)).map((m) => {
    const mx = xOf(m);
    let row = lastX.findIndex((lx) => mx - lx >= LABEL_W);
    if (row < 0) row = Math.min(lastX.length, 2);
    lastX[row] = mx;
    return { m, row };
  });
}

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
  const h = hover != null ? points[hover] : null;

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
          const px = e.clientX - e.currentTarget.getBoundingClientRect().left - left;
          setHover(Math.max(0, Math.min(points.length - 1, Math.round((px / innerW) * (points.length - 1)))));
        }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
            <text x={left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize="11" fill="var(--text-3)" className="num">{fmt(t)}</text>
          </g>
        ))}
        {[...new Set([0, points.length - 1])].map((i) => (
          <text key={i} x={x(i)} y={height - 6} textAnchor={i === 0 ? "start" : "end"} fontSize="11" fill="var(--text-3)">{fmtTime(points[i].t)}</text>
        ))}
        {refLines.map((r) => (
          <g key={r.label}>
            <line x1={left} x2={width - right} y1={y(r.value)} y2={y(r.value)} stroke={`var(--${r.tone})`} strokeWidth="1.5" strokeDasharray="5 4" />
            <text x={width - right} y={y(r.value) - 6} textAnchor="end" fontSize="11" fill="var(--text-2)">{r.label}</text>
          </g>
        ))}
        <path d={path} fill="none" stroke="var(--text)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {placeLabels(marks.filter((m) => points[m.i]), (m) => x(m.i)).map(({ m, row }) => {
          const after = points[m.i].v;
          const before = after - m.delta;
          const top = Math.min(y(before), y(after));
          const bottom = Math.max(y(before), y(after));
          const mx = x(m.i);
          const nearRight = mx > width - right - 120;
          // Labels that would overlap a neighbour's move one line further from the bar.
          const labelY = m.delta < 0 ? bottom + 14 + row * 13 : top - 6 - row * 13;
          return (
            <g key={`${m.i}-${m.label}`}>
              <line x1={mx} x2={mx} y1={12} y2={12 + innerH} stroke="var(--border)" strokeDasharray="3 3" />
              <rect x={mx - 3} y={top} width="6" height={Math.max(2, bottom - top)} rx="2" fill="var(--text-2)" />
              <text x={nearRight ? mx - 8 : mx + 8} y={labelY} textAnchor={nearRight ? "end" : "start"} fontSize="11" fill="var(--text-2)" className="num">
                {m.label}
              </text>
            </g>
          );
        })}
        {h && hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={12} y2={12 + innerH} stroke="var(--border)" />
            <circle cx={x(hover)} cy={y(h.v)} r="4.5" fill="var(--text)" stroke="var(--bg)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {h && hover != null && (
        <div
          className="pointer-events-none absolute top-0 rounded-md border border-border bg-bg px-2 py-1 text-xs shadow-sm"
          style={{ left: Math.min(Math.max(x(hover) - 60, 0), width - 140) }}
        >
          <span className="text-text-3">{fmtTime(h.t)}</span> <span className="num font-medium">{fmt(h.v)}</span>
        </div>
      )}
    </div>
  );
}
