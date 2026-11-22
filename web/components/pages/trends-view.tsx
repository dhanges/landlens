"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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

function TrendChart({ series }: { series: TrendPoint[] }) {
  const c = useChartColours();
  if (!c.primary) return <Skeleton className="h-[280px]" />;
  const data = series.map((p) => ({ yr: p.yr, median: p.median_price_sqm, guideline: p.guideline_sqm }));
  const k = (v: number) => (v >= 1000 ? `${Math.round(v / 100) / 10}k` : String(Math.round(v)));
  return (
    <div className="h-[280px]" role="img" aria-label="Median price per sq m and guideline rate by year">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 12, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid vertical={false} stroke={c.border} />
          <XAxis
            dataKey="yr"
            type="number"
            domain={["dataMin", "dataMax"]}
            allowDecimals={false}
            tick={{ fill: c.muted, fontSize: 11, fontFamily: "var(--font-plex-mono)" }}
            axisLine={{ stroke: c.border }}
            tickLine={false}
          />
          <YAxis tickFormatter={k} width={44} tick={{ fill: c.muted, fontSize: 11, fontFamily: "var(--font-plex-mono)" }} axisLine={false} tickLine={false} domain={[0, "auto"]} />
          <Tooltip
            contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, fontSize: 13, color: c.text }}
            formatter={(v, n) => [inr(Number(v)), n === "median" ? "Market median" : "Guideline rate"]}
          />
          <Legend formatter={(n) => (n === "median" ? "Market median" : "Guideline rate")} wrapperStyle={{ fontSize: 13, color: c.muted }} />
          <Line dataKey="median" stroke={c.primary} strokeWidth={2.5} dot={{ r: 3, fill: c.primary }} isAnimationActive={false} />
          <Line dataKey="guideline" stroke={c.accent} strokeWidth={2} strokeDasharray="6 4" dot={false} connectNulls isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
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
                  <span className="text-[13px] text-muted">₹ per sq m · {LAND_TYPE_LABEL[data!.land_type!]}</span>
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
