"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useChartColours } from "@/components/report/price-history";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { ToggleChip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import type { LandType, TrendPoint } from "@/lib/api";
import { clean, dash, inr, int, LAND_TYPE_LABEL, pct, pctFrac } from "@/lib/format";
import { useMandalTrend, useSearch, useVillageTrend } from "@/lib/queries";
import { cn } from "@/lib/utils";

const LAND_TYPES: LandType[] = ["urban_plot", "peri_urban", "agricultural"];

function VillagePicker({ onPick }: { onPick: (id: number) => void }) {
  const [q, setQ] = useState("");
  const [d, setD] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setD(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);
  const res = useSearch(d);
  const villages = res.data?.villages ?? [];
  return (
    <div className="relative w-full max-w-[420px]">
      <label className="flex h-10 items-center gap-2 rounded-lg border border-border bg-surface px-3 focus-within:border-primary">
        <span className="sr-only-label">Village</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Find a village, e.g. Hanamkonda"
          className="min-w-0 flex-1 border-0 bg-transparent text-[15px] outline-none placeholder:text-muted"
          data-testid="village-picker"
        />
      </label>
      {d.length >= 2 && (
        <ul className="tile absolute left-0 right-0 top-[44px] z-30 max-h-72 overflow-auto py-1 text-[14px]">
          {res.isPending ? (
            <li className="px-3 py-2 text-muted">Searching…</li>
          ) : villages.length === 0 ? (
            <li className="px-3 py-2 text-muted">No village matches “{d}”.</li>
          ) : (
            villages.map((v) => (
              <li key={v.village_id}>
                <button
                  type="button"
                  onClick={() => {
                    setQ("");
                    onPick(v.village_id);
                  }}
                  className="w-full px-3 py-2 text-left hover:bg-tint hover:text-tint-text"
                >
                  <div className="font-medium">{clean(v.name)}</div>
                  <div className="text-[12px] text-muted">{clean(v.mandal)}</div>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

export const FEW_SALES = 5;

type ChartRow = {
  yr: number;
  median: number;
  band: [number, number] | null;
  guideline: number | null;
  n: number;
};

/** One tooltip for both charts (synced by year): median, spread, sales, guideline; flags thin years. */
function TrendTooltip({ active, payload, c }: { active?: boolean; payload?: { payload: ChartRow }[]; c: ReturnType<typeof useChartColours> }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return (
    <div
      className="rounded-lg px-3 py-2 text-[13px]"
      style={{ background: c.surface, border: `1px solid ${c.border}`, color: c.text, boxShadow: "var(--shadow-card)" }}
    >
      <div className="num mb-1 font-medium">{row.yr}</div>
      <div>
        Median <span className="num">{inr(row.median)}</span>
      </div>
      {row.band && row.band[0] !== row.band[1] && (
        <div style={{ color: c.muted }}>
          Middle half <span className="num">{inr(row.band[0])}–{inr(row.band[1]).slice(1)}</span>
        </div>
      )}
      {row.guideline != null && (
        <div style={{ color: c.muted }}>
          Guideline <span className="num">{inr(row.guideline)}</span>
        </div>
      )}
      <div>
        <span className="num">{int(row.n)}</span> {row.n === 1 ? "sale" : "sales"}
      </div>
      {row.n < FEW_SALES && (
        <div className="mt-1 font-medium" style={{ color: c.down }}>
          Few sales, median less reliable
        </div>
      )}
    </div>
  );
}

/**
 * Price chart (median line over a p25-p75 band, guideline dashed) and, under it, a sales-volume bar chart on the
 * same year axis. Both use a numeric year axis with the same domain, margins and y-axis width so bars line up
 * with the line's points; each chart shows the shared tooltip for the hovered year.
 */
function TrendChart({ series }: { series: TrendPoint[] }) {
  const c = useChartColours();
  if (!c.primary)
    return (
      <div aria-busy="true">
        <Skeleton className="h-[280px]" />
        <Skeleton className="mt-3 h-[110px]" />
      </div>
    );
  const data: ChartRow[] = series.map((p) => ({
    yr: p.yr,
    median: p.median_price_sqm,
    band: p.p25_price_sqm != null && p.p75_price_sqm != null ? [p.p25_price_sqm, p.p75_price_sqm] : null,
    guideline: p.guideline_sqm,
    n: p.n_sales,
  }));
  const k = (v: number) => (v >= 1000 ? `${Math.round(v / 100) / 10}k` : String(Math.round(v)));
  const lo = Math.min(...data.map((d) => d.yr));
  const hi = Math.max(...data.map((d) => d.yr));
  const domain: [number, number] = [lo - 0.5, hi + 0.5];
  const ticks = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i).filter(
    (_, i, a) => a.length <= 10 || i % 2 === 0 || i === a.length - 1,
  );
  const axisTick = { fill: c.muted, fontSize: 11, fontFamily: "var(--font-plex-mono)" };
  const margin = { top: 12, right: 12, bottom: 4, left: 4 };
  const thin = data.some((d) => d.n < FEW_SALES);
  return (
    <div>
      <div className="h-[280px]" role="img" aria-label="Median price per sq m by year with the middle half of sale prices shaded, and the guideline rate">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={margin}>
            <CartesianGrid vertical={false} stroke={c.border} />
            <XAxis dataKey="yr" type="number" domain={domain} ticks={ticks} allowDecimals={false} tick={axisTick} axisLine={{ stroke: c.border }} tickLine={false} />
            <YAxis tickFormatter={k} width={48} tick={axisTick} axisLine={false} tickLine={false} domain={[0, "auto"]} />
            <Tooltip content={<TrendTooltip c={c} />} cursor={{ stroke: c.border }} />
            <Legend
              formatter={(n) => (n === "band" ? "Middle half of sales (p25–p75)" : n === "median" ? "Market median" : "Guideline rate")}
              wrapperStyle={{ fontSize: 13, color: c.muted }}
            />
            <Area dataKey="band" stroke="none" fill={c.primary} fillOpacity={0.16} isAnimationActive={false} connectNulls legendType="square" />
            <Line dataKey="guideline" stroke={c.accent} strokeWidth={2} strokeDasharray="6 4" dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="median" stroke={c.primary} strokeWidth={2.5} dot={{ r: 3, fill: c.primary }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1 h-[110px]" role="img" aria-label="Number of sales per year">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ ...margin, top: 4 }}>
            <CartesianGrid vertical={false} stroke={c.border} />
            <XAxis dataKey="yr" type="number" domain={domain} ticks={ticks} allowDecimals={false} tick={axisTick} axisLine={{ stroke: c.border }} tickLine={false} />
            <YAxis width={48} tick={axisTick} axisLine={false} tickLine={false} allowDecimals={false} tickFormatter={(v: number) => (v >= 1000 ? `${Math.round(v / 100) / 10}k` : String(v))} />
            <Tooltip content={<TrendTooltip c={c} />} cursor={{ fill: c.border, fillOpacity: 0.4 }} />
            <Bar dataKey="n" isAnimationActive={false} maxBarSize={28} radius={[2, 2, 0, 0]}>
              {data.map((d) => (
                <Cell key={d.yr} fill={c.muted} fillOpacity={d.n < FEW_SALES ? 0.25 : 0.5} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[12px] text-muted">
        Bars: sales per year{thin ? `; lighter bars have fewer than ${FEW_SALES} sales, so that year's median is less reliable` : ""}.
      </p>
    </div>
  );
}

/** Locality trends (J4, FR-5): median price per sq m by year, sale count, YoY with its base year, guideline gap. */
export function TrendsView() {
  const router = useRouter();
  const path = usePathname();
  const params = useSearchParams();
  const villageId = Number(params.get("village")) || null;
  const level = params.get("level") === "mandal" ? "mandal" : "village";
  const ltParam = params.get("land_type") as LandType | null;
  const lt = ltParam && LAND_TYPES.includes(ltParam) ? ltParam : undefined;
  const village = useVillageTrend(villageId, lt);
  const mandalId = village.data?.mandal_id ?? null;
  const mandal = useMandalTrend(level === "mandal" ? mandalId : null, lt ?? village.data?.land_type ?? undefined);
  const q = level === "mandal" ? mandal : village;
  const data = q.data;

  const go = (p: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(p)) v == null ? next.delete(k) : next.set(k, v);
    router.replace(`${path}?${next.toString()}`, { scroll: false });
  };

  const series = data?.series ?? [];
  const last = series.at(-1);
  const gap = last?.guideline_sqm && last.median_price_sqm ? (last.guideline_sqm / last.median_price_sqm - 1) * 100 : null;

  return (
    <div className="mx-auto max-w-page px-8 pb-14 pt-10">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[44px] leading-tight tracking-display">
            {village.data ? `${clean(level === "mandal" ? (mandal.data?.name ?? "") : village.data.name)}` : "Locality trends"}
          </h1>
          <p className="text-muted">
            {village.data
              ? level === "mandal"
                ? `Mandal of ${clean(village.data.name)} · median price per sq m by year`
                : "Village · median price per sq m by year"
              : "Median price per sq m by year, the sale count, year-on-year change and the guideline-rate gap."}
          </p>
        </div>
        <VillagePicker onPick={(id) => go({ village: String(id), level: null })} />
      </div>

      {!villageId ? (
        <div className="card">
          <EmptyState title="Pick a village" hint="Search above, or open a parcel report and follow Locality trends." />
        </div>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-2">
            {LAND_TYPES.map((t) => (
              <ToggleChip key={t} selected={(lt ?? data?.land_type) === t} onClick={() => go({ land_type: t })}>
                {LAND_TYPE_LABEL[t]}
              </ToggleChip>
            ))}
            <span className="mx-2 h-5 w-px bg-border" aria-hidden="true" />
            <ToggleChip selected={level === "village"} onClick={() => go({ level: null })}>
              Village
            </ToggleChip>
            <ToggleChip selected={level === "mandal"} onClick={() => go({ level: "mandal" })} disabled={!mandalId}>
              Whole mandal
            </ToggleChip>
          </div>

          {q.isPending ? (
            <div className="card p-6">
              <Skeleton className="mb-4 h-[280px]" />
              <SkeletonRows rows={5} />
            </div>
          ) : q.isError ? (
            <ErrorState error={q.error} title="This trend could not load" onRetry={() => q.refetch()} className="card" />
          ) : series.length === 0 ? (
            <div className="card">
              <EmptyState
                title="No sales recorded"
                hint={`There are no ${data?.land_type ? LAND_TYPE_LABEL[data.land_type].toLowerCase() : ""} sales here. Try another land type.`}
              />
            </div>
          ) : (
            <>
              <div className="mb-6 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
                <div className="tile p-4">
                  <div className="text-[13px] text-muted">Median, {last!.yr}</div>
                  <div className="num text-[22px] font-medium">{inr(last!.median_price_sqm)}</div>
                  <div className="text-[13px] text-muted">per sq m, {int(last!.n_sales)} sales</div>
                </div>
                <div className="tile p-4">
                  <div className="text-[13px] text-muted">Year on year</div>
                  <div className={cn("num text-[22px] font-medium", last!.yoy == null ? "text-muted" : last!.yoy >= 0 ? "text-up" : "text-down")}>
                    {pctFrac(last!.yoy)}
                  </div>
                  <div className="text-[13px] text-muted">{last!.yoy_base_yr ? `against ${last!.yoy_base_yr}` : "no earlier year"}</div>
                </div>
                <div className="tile p-4">
                  <div className="text-[13px] text-muted">Guideline rate</div>
                  <div className="num text-[22px] font-medium">{inr(last!.guideline_sqm)}</div>
                  <div className="text-[13px] text-muted">
                    {gap == null ? "no rate on record" : `${Math.abs(Math.round(gap))}% ${gap < 0 ? "below" : "above"} the market median`}
                  </div>
                </div>
              </div>

              <section className="card mb-6 p-6">
                <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="text-[26px]">Price history</h2>
                  <span className="text-[13px] text-muted">₹ per sq m and sales per year · {LAND_TYPE_LABEL[data!.land_type!]}</span>
                </div>
                <TrendChart series={series} />
              </section>

              <div className="tile overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-[14px]" data-testid="trend-table">
                  <thead>
                    <tr className="text-left text-[12px] text-muted">
                      <th className="border-b border-border px-[14px] py-2.5 font-medium">Year</th>
                      <th className="border-b border-border px-[14px] py-2.5 text-right font-medium">Median ₹ / sq m</th>
                      <th className="border-b border-border px-[14px] py-2.5 text-right font-medium">Sales</th>
                      <th className="border-b border-border px-[14px] py-2.5 text-right font-medium">Year on year</th>
                      <th className="border-b border-border px-[14px] py-2.5 text-right font-medium">Guideline ₹ / sq m</th>
                      <th className="border-b border-border px-[14px] py-2.5 text-right font-medium">Guideline vs market</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...series].reverse().map((p) => {
                      const g = p.guideline_sqm ? (p.guideline_sqm / p.median_price_sqm - 1) * 100 : null;
                      const skipped = p.yoy_base_yr != null && p.yoy_base_yr < p.yr - 1;
                      return (
                        <tr key={p.yr}>
                          <td className="num border-b border-border px-[14px] py-2.5">{p.yr}</td>
                          <td className="num border-b border-border px-[14px] py-2.5 text-right">{inr(p.median_price_sqm)}</td>
                          <td className="num border-b border-border px-[14px] py-2.5 text-right">{int(p.n_sales)}</td>
                          <td className={cn("num border-b border-border px-[14px] py-2.5 text-right", p.yoy == null ? "text-muted" : p.yoy >= 0 ? "text-up" : "text-down")}>
                            {pctFrac(p.yoy)}
                            {skipped && <span className="ml-1 text-[12px] text-muted">vs {p.yoy_base_yr}</span>}
                          </td>
                          <td className="num border-b border-border px-[14px] py-2.5 text-right">{p.guideline_sqm ? inr(p.guideline_sqm) : dash}</td>
                          <td className="num border-b border-border px-[14px] py-2.5 text-right">{pct(g, 0)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-[13px] text-muted">
                Years without sales are left out; year-on-year then compares with the last year that had sales. Synthetic sales and
                guideline rates. <Link href="/map">Find parcels in this area</Link>.
              </p>
            </>
          )}
        </>
      )}
    </div>
  );
}
