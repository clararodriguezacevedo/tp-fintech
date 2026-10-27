// Number and date formatting, Argentine style (1.234,56).

const ars = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const compact = new Intl.NumberFormat("es-AR", { notation: "compact", maximumFractionDigits: 1 });
const int = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

export const money = (x: number | null | undefined) => (x == null ? "-" : `$ ${ars.format(x)}`);
export const moneyCompact = (x: number | null | undefined) => (x == null ? "-" : `$ ${compact.format(x)}`);
export const price = (x: number | null | undefined) => (x == null ? "-" : ars.format(x));
export const integer = (x: number | null | undefined) => (x == null ? "-" : int.format(x));

/** Round each value to `digits` decimals so the rounded values still add up to the rounded
 * total (largest remainder): a column of percentages that sums to 100, a breakdown that sums to
 * its score. */
export function roundToTotal(values: number[], digits = 0, total = values.reduce((s, v) => s + v, 0)) {
  const k = 10 ** digits;
  const target = Math.round(total * k);
  const floors = values.map((v) => Math.floor(v * k));
  let left = target - floors.reduce((s, v) => s + v, 0);
  const order = values.map((v, i) => [v * k - floors[i], i] as const).sort((a, b) => b[0] - a[0]);
  const out = [...floors];
  for (const [, i] of left >= 0 ? order : [...order].reverse()) {
    if (left === 0) break;
    out[i] += left > 0 ? 1 : -1;
    left += left > 0 ? -1 : 1;
  }
  return out.map((v) => v / k);
}

/** 0.0523 -> "+5,2%" */
export const pct = (x: number | null | undefined, digits = 1) =>
  x == null ? "-" : `${x > 0 ? "+" : ""}${(x * 100).toLocaleString("es-AR", { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;

/** 5.23 (already a percent) -> "+5,2%" */
export const pctPoints = (x: number | null | undefined, digits = 1) =>
  x == null ? "-" : `${x > 0 ? "+" : ""}${x.toLocaleString("es-AR", { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;

/** Probability 0..1 -> "62%" */
export const prob = (x: number | null | undefined) => (x == null ? "-" : `${Math.round(x * 100)}%`);

/** Score -1..1 -> "+0,64" */
export const score = (x: number) => `${x > 0 ? "+" : ""}${x.toLocaleString("es-AR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;

const AR = "America/Argentina/Buenos_Aires";

export const dayLong = (d: Date | string) =>
  new Date(d).toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: AR });

export const dayShort = (d: Date | string) =>
  new Date(d).toLocaleDateString("es-AR", { day: "numeric", month: "short", timeZone: AR });

export const dateTime = (d: Date | string) =>
  new Date(d).toLocaleString("es-AR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: AR });

export const timeAgo = (d: Date | string) => {
  const mins = Math.round((Date.now() - new Date(d).getTime()) / 60000);
  if (mins < 1) return "recién";
  if (mins < 60) return `hace ${mins} min`;
  const h = Math.round(mins / 60);
  if (h < 48) return `hace ${h} h`;
  return `hace ${Math.round(h / 24)} días`;
};
