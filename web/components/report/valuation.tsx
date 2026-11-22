"use client";

import { useState } from "react";

import { Input } from "@/components/ui/input";
import type { Report } from "@/lib/api";
import { area, clean, dist, inr, int, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

const DRIVER_LABEL = (r: Report, k: string): string => {
  const loc = r.location;
  const near = loc.nearest_active_project;
  switch (k) {
    case "area":
      return `Plot size against the comparables, ${area(loc.area_sqm)}`;
    case "frontage":
      return loc.road_frontage_m > 0 ? `Road frontage, ${int(loc.road_frontage_m)} m` : "No road frontage";
    case "project":
      return near
        ? `Distance to ${clean(near.name)}, ${dist(loc.distances_m.active_project)}`
        : "Distance to an active project";
    case "time":
      return `Time adjustment to ${r.valuation.as_of.slice(0, 4)}`;
    default:
      return k;
  }
};

/** Valuation (Report mockup): range bar (p25-p75 band, p50 in sage, asking in walnut) and signed drivers. */
export function ValuationSection({ r }: { r: Report }) {
  const v = r.valuation;
  const [asking, setAsking] = useState("");
  const askingN = Number(asking.replace(/[^\d.]/g, "")) || null;

  const months = v.search_months;
  const km = v.search_radius_m / 1000;
  const lead =
    v.confidence === "none"
      ? `Only ${v.n_comparables} comparable ${v.n_comparables === 1 ? "sale" : "sales"} within ${km} km in the last ${months} months, so no range is given.`
      : `From ${v.n_comparables} comparable sales within ${km} km in the last ${months} months. Confidence: ${v.confidence}.`;

  let bar: React.ReactNode = null;
  if (v.p25_sqm != null && v.p50_sqm != null && v.p75_sqm != null) {
    const adj = r.comparables.map((c) => c.adjusted_price_sqm);
    const lo0 = Math.min(v.p25_sqm, ...adj, askingN ?? Infinity);
    const hi0 = Math.max(v.p75_sqm, ...adj, askingN ?? -Infinity);
    const padding = (hi0 - lo0) * 0.08 || v.p50_sqm * 0.1;
    const lo = Math.max(0, lo0 - padding);
    const hi = hi0 + padding;
    const at = (x: number) => `${(((x - lo) / (hi - lo)) * 100).toFixed(2)}%`;
    bar = (
      <>
        <div className="relative mx-2 mb-2 h-10" role="img" aria-label={`Fair value p25 ${inr(v.p25_sqm)}, median ${inr(v.p50_sqm)}, p75 ${inr(v.p75_sqm)} per sq m`}>
          <div className="absolute left-0 right-0 top-4 h-2 rounded bg-border" />
          <div
            className="absolute top-4 h-2 rounded bg-heat-2"
            style={{ left: at(v.p25_sqm), width: `calc(${at(v.p75_sqm)} - ${at(v.p25_sqm)})` }}
          />
          <div className="absolute top-2 h-6 w-[3px] bg-primary" style={{ left: at(v.p50_sqm) }} />
          {askingN && <div className="absolute top-2 h-6 w-[3px] bg-accent" style={{ left: at(askingN) }} />}
        </div>
        <div className="num mx-2 mb-5 flex flex-wrap justify-between gap-x-3 text-[12px] text-muted">
          <span>{inr(lo)}</span>
          <span>p25 {inr(v.p25_sqm)}</span>
          {askingN && <span className="text-accent">asking {inr(askingN)}</span>}
          <span className="text-primary">p50 {inr(v.p50_sqm)}</span>
          <span>p75 {inr(v.p75_sqm)}</span>
          <span>{inr(hi)}</span>
        </div>
      </>
    );
  }

  const askVsP50 = askingN && v.p50_sqm ? (askingN / v.p50_sqm - 1) * 100 : null;

  return (
    <section className="card p-6" aria-labelledby="valuation-h">
      <h2 id="valuation-h" className="mb-1 text-[26px]">
        Valuation
      </h2>
      <p className="mb-5 text-muted">{lead}</p>
      {v.note && v.confidence !== "none" && <p className="-mt-3 mb-5 text-[13px] text-muted">{v.note}</p>}
      {bar ?? (
        <div className="mb-5 rounded-lg bg-bg px-4 py-3 text-[15px]">
          Locality median: <span className="num font-medium">{v.locality_median_sqm == null ? "no recent sales" : `${inr(v.locality_median_sqm)} per sq m`}</span>
        </div>
      )}
      {bar && (
        <label className="no-print mb-5 flex flex-wrap items-center gap-2 text-[13px] text-muted">
          Compare an asking price
          <span className="relative">
            <span className="num absolute left-2.5 top-1/2 -translate-y-1/2 text-text">₹</span>
            <Input
              inputMode="numeric"
              value={asking}
              onChange={(e) => setAsking(e.target.value)}
              placeholder="per sq m"
              className="num h-8 w-36 pl-6 text-[13px]"
              aria-label="Asking price per sq m"
            />
          </span>
          {askVsP50 != null && (
            <span className="num text-text">
              {pct(askVsP50)} against p50
            </span>
          )}
        </label>
      )}
      {v.drivers.length > 0 && (
        <>
          <div className="mb-2 text-[13px] text-muted">What moves the value (median effect on the comparables)</div>
          {v.drivers.map((d) => (
            <div key={d.factor} className="flex justify-between gap-4 border-t border-border py-[9px]">
              <span>{DRIVER_LABEL(r, d.factor)}</span>
              <span
                className={cn(
                  "num",
                  d.median_effect_pct > 0 ? "text-up" : d.median_effect_pct < 0 ? "text-down" : "text-muted",
                )}
              >
                {pct(d.median_effect_pct)}
              </span>
            </div>
          ))}
        </>
      )}
    </section>
  );
}
