/** Number formatting for the UI: Indian digit grouping, a real minus sign, units as in the mockups. */

const MINUS = "−";
const nf0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const signed = (s: string, v: number) => (v < 0 ? `${MINUS}${s.replace("-", "")}` : v > 0 ? `+${s}` : s);
export const dash = "—";

export function int(v: number | null | undefined): string {
  return v == null ? dash : nf0.format(v).replace("-", MINUS);
}

/** ₹16,980 */
export function inr(v: number | null | undefined): string {
  return v == null ? dash : `₹${int(v)}`;
}

/** ₹16,900–19,800 */
export function inrRange(a: number | null | undefined, b: number | null | undefined): string {
  if (a == null || b == null) return dash;
  return `₹${int(a)}–${int(b)}`;
}

/** Totals: ₹3.13 cr, ₹42.5 lakh, ₹85,000. */
export function inrShort(v: number | null | undefined): string {
  if (v == null) return dash;
  if (Math.abs(v) >= 1e7) return `₹${nf2.format(v / 1e7)} cr`;
  if (Math.abs(v) >= 1e5) return `₹${nf1.format(v / 1e5)} lakh`;
  return inr(v);
}

/** ₹3.13–3.66 cr (both ends in the larger unit). */
export function inrShortRange(a: number | null | undefined, b: number | null | undefined): string {
  if (a == null || b == null) return dash;
  if (Math.max(a, b) >= 1e7) return `₹${nf2.format(a / 1e7)}–${nf2.format(b / 1e7)} cr`;
  if (Math.max(a, b) >= 1e5) return `₹${nf1.format(a / 1e5)}–${nf1.format(b / 1e5)} lakh`;
  return inrRange(a, b);
}

/** A fraction as a signed percentage: 0.124 -> +12.4% */
export function pctFrac(v: number | null | undefined, digits = 1): string {
  if (v == null) return dash;
  const s = `${(v * 100).toFixed(digits)}%`;
  return signed(s, Number((v * 100).toFixed(digits)));
}

/** Already a percentage: -1.63 -> −1.6% */
export function pct(v: number | null | undefined, digits = 1): string {
  if (v == null) return dash;
  const s = `${v.toFixed(digits)}%`;
  return signed(s, Number(v.toFixed(digits)));
}

/** 640 m, 1.2 km, 12 km */
export function dist(m: number | null | undefined): string {
  if (m == null) return dash;
  if (m < 1000) return `${Math.round(m / 10) * 10} m`;
  if (m < 10_000) return `${(m / 1000).toFixed(1)} km`;
  return `${Math.round(m / 1000)} km`;
}

export const area = (sqm: number | null | undefined) => (sqm == null ? dash : `${int(sqm)} sq m`);

export function survey(s: { survey_no?: string | null; sub_div?: string | null }): string {
  if (!s.survey_no) return dash;
  return s.sub_div ? `${s.survey_no}/${s.sub_div}` : s.survey_no;
}

export const LAND_TYPE_LABEL: Record<string, string> = {
  urban_plot: "Urban plot",
  peri_urban: "Peri-urban",
  agricultural: "Agricultural",
};

export const GW_LABEL: Record<string, string> = {
  safe: "Safe",
  semi_critical: "Semi-critical",
  critical: "Critical",
  over_exploited: "Over-exploited",
};

/** "[fallback] Residential" -> "Residential" (the fallback marker becomes a badge in the UI). */
export function clean(name: string | null | undefined): string {
  if (!name) return dash;
  return name.startsWith("[fallback] ") ? name.slice(11) : name;
}
export const isFallback = (name: string | null | undefined) => !!name?.startsWith("[fallback] ");

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-03-14" -> "Mar 2026" */
export function monthYear(iso: string | null | undefined): string {
  if (!iso) return dash;
  const [y, m] = iso.split("-");
  return `${MONTHS[Number(m) - 1]} ${y}`;
}
/** "2026-11-22T09:37:20Z" -> "22 Nov 2026, 15:07" in the viewer's zone */
export function dateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes(),
  ).padStart(2, "0")}`;
}
