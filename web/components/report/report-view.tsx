"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useState } from "react";

import { ChatPanel } from "@/components/chat/chat-panel";
import { PriceHistory } from "@/components/report/price-history";
import { ValuationSection } from "@/components/report/valuation";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Chip, SyntheticBadge } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import * as api from "@/lib/api";
import {
  area,
  clean,
  dash,
  dist,
  GW_LABEL,
  inr,
  inrRange,
  inrShortRange,
  int,
  isFallback,
  LAND_TYPE_LABEL,
  monthYear,
  pct,
  pctFrac,
  survey,
} from "@/lib/format";
import { keys, useMe, useReport, useSummary } from "@/lib/queries";
import { cn } from "@/lib/utils";

function Tile({ label, value, sub, valueClass }: { label: string; value: React.ReactNode; sub?: React.ReactNode; valueClass?: string }) {
  return (
    <div className="tile p-4">
      <div className="text-[13px] text-muted">{label}</div>
      <div className={cn("num text-[22px] font-medium leading-snug", valueClass)}>{value}</div>
      {sub && <div className="text-[13px] text-muted">{sub}</div>}
    </div>
  );
}

function Locked() {
  return (
    <span className="inline-flex items-center gap-1.5 text-muted">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <rect x="5" y="11" width="14" height="10" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </svg>
      <span className="font-sans text-[15px] font-normal">In the full report</span>
    </span>
  );
}

function Rows({ rows }: { rows: [string, React.ReactNode, string?][] }) {
  return (
    <>
      {rows.map(([k, v, cls]) => (
        <div key={k} className="flex justify-between gap-4 border-t border-border py-2 text-[15px]">
          <span className="text-muted">{k}</span>
          <span className={cn("text-right", cls)}>{v}</span>
        </div>
      ))}
    </>
  );
}

/** Parcel report page (J2): free summary, locked preview with the unlock flow, then the full report. */
export function ReportView({ id }: { id: number }) {
  const summary = useSummary(id);
  const me = useMe();
  const unlocked = !!summary.data?.unlocked;
  const report = useReport(id, unlocked);

  if (summary.isPending) return <ReportSkeleton />;
  if (summary.isError) {
    const e = summary.error;
    if (e instanceof api.ApiError && (e.status === 404 || e.status === 422))
      return (
        <EmptyState
          title="No parcel with this number"
          hint="The link may be mistyped. Find the parcel on the map or by survey number."
          action={
            <Button asChild variant="outline">
              <Link href="/map">Open the map</Link>
            </Button>
          }
          className="py-24"
        />
      );
    return <ErrorState error={e} title="This parcel could not load" onRetry={() => summary.refetch()} className="py-24" />;
  }

  const s = summary.data;
  const r = report.data;
  const last = r?.locality_trend.series.at(-1);
  const guideline = last?.guideline_sqm ?? null;
  const gap = guideline != null && s.village_median_sqm ? (guideline / s.village_median_sqm - 1) * 100 : null;

  return (
    <div className="mx-auto max-w-page px-8 pb-14 pt-7">
      <div className="mb-2.5 text-[13px] text-muted">
        <Link href="/map" className="no-underline">
          Map
        </Link>{" "}
        / {clean(s.mandal)} mandal / {clean(s.village)}
      </div>
      <div className="mb-6 flex flex-wrap items-end gap-4">
        <div className="min-w-0 flex-[1_1_480px]">
          <h1 className="mb-1.5 text-[44px] leading-[1.1] tracking-display">
            Survey {survey(s)}, {clean(s.village)}
          </h1>
          <div className="flex flex-wrap gap-2">
            <Chip tone="tint">{LAND_TYPE_LABEL[s.land_type]}</Chip>
            <Chip>{area(s.area_sqm)}</Chip>
            {r && r.location.road_frontage_m > 0 && <Chip>{int(r.location.road_frontage_m)} m road frontage</Chip>}
            {s.zone_name && <Chip>{clean(s.zone_name)} zone</Chip>}
            {s.source === "synthetic" && <Chip tone="muted">Sample data</Chip>}
          </div>
        </div>
        <div className="no-print flex gap-2.5">
          <Button asChild variant="outline">
            <Link href={`/trends?village=${s.village_id}&land_type=${s.land_type}`}>Locality trends</Link>
          </Button>
          {unlocked && (
            <Button variant="primary" onClick={() => window.print()} disabled={!r}>
              Print to PDF
            </Button>
          )}
        </div>
      </div>

      <div className="mb-7 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
        <Tile
          label="Fair value range"
          value={r ? (r.valuation.p25_sqm != null ? inrRange(r.valuation.p25_sqm, r.valuation.p75_sqm) : "No range") : unlocked ? <Skeleton className="mt-1 h-7 w-40" /> : <Locked />}
          sub={
            r
              ? r.valuation.p25_inr != null
                ? `per sq m · ${inrShortRange(r.valuation.p25_inr, r.valuation.p75_inr)} total`
                : "fewer than 3 comparable sales"
              : "per sq m, from comparable sales"
          }
        />
        <Tile
          label="Village median"
          value={inr(s.village_median_sqm)}
          sub={s.village_median_sqm == null ? "no sales in 36 months" : "per sq m, last 36 months"}
        />
        <Tile
          label="5-year growth"
          value={s.cagr_5y == null ? dash : `${pctFrac(s.cagr_5y)} a year`}
          valueClass={s.cagr_5y == null ? "text-muted" : s.cagr_5y >= 0 ? "text-up" : "text-down"}
          sub={`${LAND_TYPE_LABEL[s.land_type].toLowerCase()}, ${clean(s.village)}`}
        />
        <Tile
          label="Guideline rate"
          value={r ? inr(guideline) : unlocked ? <Skeleton className="mt-1 h-7 w-28" /> : <Locked />}
          sub={
            r
              ? gap == null
                ? "no rate on record"
                : `${pct(Math.abs(gap), 0).replace(/^[+−]/, "")} ${gap < 0 ? "below" : "above"} market median`
              : "government rate per sq m"
          }
        />
      </div>

      {!unlocked ? (
        <UnlockPanel s={s} me={me.data ?? null} meLoading={me.isPending} />
      ) : report.isPending ? (
        <SectionsSkeleton />
      ) : report.isError ? (
        <ErrorState error={report.error} title="The report could not load" onRetry={() => report.refetch()} className="card" />
      ) : (
        <FullReport r={report.data} />
      )}
    </div>
  );
}

function UnlockPanel({ s, me, meLoading }: { s: api.ParcelSummary; me: api.User | null; meLoading: boolean }) {
  const qc = useQueryClient();
  const keyRef = useRef<string | null>(null);
  const [done, setDone] = useState(false);
  const next = encodeURIComponent(`/parcels/${s.parcel_id}`);
  const unlock = useMutation({
    mutationFn: () => {
      // one key per attempt: a retry after a network error or 503 reuses it, so it can never charge twice
      keyRef.current ??= api.newIdempotencyKey();
      return api.unlockReport(s.parcel_id, keyRef.current);
    },
    onSuccess: (res) => {
      keyRef.current = null;
      setDone(true);
      qc.setQueryData<api.User | null>(keys.me, (u) => (u ? { ...u, credit_balance: res.credit_balance } : u));
      qc.setQueryData<api.ParcelSummary>(keys.summary(s.parcel_id), (old) => (old ? { ...old, unlocked: true } : old));
      qc.invalidateQueries({ queryKey: keys.ledger });
    },
    onError: (e) => {
      if (e instanceof api.ApiError && e.status !== 503 && e.status !== 0) keyRef.current = null;
    },
  });
  const err = unlock.error instanceof api.ApiError ? unlock.error : null;
  const included = [
    "Fair value range from comparable sales, with every adjustment",
    "Price history and the comparable sales table",
    "Zoning, permitted uses and the source clause",
    "Soil and groundwater, distances to roads, water and projects",
  ];

  return (
    <section className="card grid gap-6 p-6 md:grid-cols-[1fr_320px]" aria-labelledby="unlock-h" data-testid="unlock-panel">
      <div>
        <h2 id="unlock-h" className="mb-1 text-[26px]">
          Unlock the full report
        </h2>
        <p className="mb-4 text-muted">One credit unlocks this parcel for good. You can read it again at any time.</p>
        <ul className="flex flex-col gap-2 text-[15px]">
          {included.map((t) => (
            <li key={t} className="flex gap-2">
              <span className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />
              {t}
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-col justify-center gap-3 rounded-tile bg-bg p-5">
        {meLoading ? (
          <Skeleton className="h-11 w-full" />
        ) : !me ? (
          <>
            <p className="text-[14px] text-muted">Create a free account to get 3 report credits.</p>
            <Button asChild variant="primary" size="block">
              <Link href={`/signup?next=${next}`}>Sign up and unlock · 1 credit</Link>
            </Button>
            <Link href={`/login?next=${next}`} className="text-center text-[14px]">
              I already have an account
            </Link>
          </>
        ) : me.credit_balance < 1 && !done ? (
          <>
            <p className="text-[14px]">
              You have <span className="num">0</span> credits left.
            </p>
            <Button asChild variant="primary" size="block">
              <Link href={`/pricing?next=${next}`}>Buy credits</Link>
            </Button>
          </>
        ) : (
          <>
            <p className="text-[14px]">
              You have <span className="num">{me.credit_balance}</span> {me.credit_balance === 1 ? "credit" : "credits"}.
              Unlocking uses one.
            </p>
            <Button
              variant="primary"
              size="block"
              onClick={() => unlock.mutate()}
              disabled={unlock.isPending || done}
              data-testid="unlock-button"
            >
              {unlock.isPending ? "Unlocking…" : "Unlock full report · 1 credit"}
            </Button>
          </>
        )}
        {err && (
          <p role="alert" className="text-[14px] text-down">
            {err.code === "insufficient_credits" ? (
              <>
                Not enough credits. <Link href={`/pricing?next=${next}`}>Buy credits</Link> to continue.
              </>
            ) : err.status === 503 || err.status === 0 ? (
              <>
                {err.message} Press unlock again: you will not be charged twice.
              </>
            ) : err.code === "auth_required" ? (
              <>
                Your session ended. <Link href={`/login?next=${next}`}>Sign in again</Link>.
              </>
            ) : (
              err.message
            )}
          </p>
        )}
      </div>
    </section>
  );
}

function FullReport({ r }: { r: api.Report }) {
  const [allComps, setAllComps] = useState(false);
  const loc = r.location;
  const projects = loc.projects_within_10km;
  const anchor =
    projects.find((p) => p.project_id === loc.nearest_active_project?.project_id && p.announced_on) ??
    projects.find((p) => p.announced_on) ??
    null;
  const env = r.environment;
  const gwTrend = env.groundwater.trend;
  const gwDir =
    gwTrend.length >= 2
      ? gwTrend.at(-1)!.extraction_pct > gwTrend[0].extraction_pct
        ? "rising"
        : gwTrend.at(-1)!.extraction_pct < gwTrend[0].extraction_pct
          ? "falling"
          : "steady"
      : null;
  const gwCat = env.groundwater.latest_category;
  const synthetic = r.provenance.synthetic_fields;
  const z = r.zoning;
  const clause = z.source_clause;
  const agriFirst = r.section_order[0] === "environment";
  const comps = allComps ? r.comparables : r.comparables.slice(0, 4);

  const soilWater = (
    <section className="card p-6" aria-labelledby="soil-h">
      <h2 id="soil-h" className="mb-3 text-[22px]">
        Soil and water
      </h2>
      <Rows
        rows={[
          ...(env.soil
            ? ([["Soil score", <span key="s" className="num">{env.soil.soil_score == null ? dash : `${Math.round(env.soil.soil_score)} / 100`}</span>]] as [string, React.ReactNode][])
            : []),
          [
            "Groundwater",
            gwCat ? `${GW_LABEL[gwCat]}${gwDir ? `, ${gwDir}` : ""}` : "No assessment",
            gwCat && gwCat !== "safe" ? "text-down" : undefined,
          ],
          ["Nearest water body", <span key="w" className="num">{dist(loc.distances_m.water)}</span>],
          ...(env.soil?.nearest_samples[0]
            ? ([["Nearest soil sample", `${env.soil.nearest_samples[0].texture}, pH ${env.soil.nearest_samples[0].ph}`]] as [string, React.ReactNode][])
            : []),
        ]}
      />
      {(synthetic.includes("soil") || synthetic.includes("groundwater")) && <SyntheticBadge className="mt-3" />}
    </section>
  );

  const zoning = (
    <section className="card p-6" aria-labelledby="zoning-h">
      <h2 id="zoning-h" className="mb-3 text-[22px]">
        Zoning
      </h2>
      <Rows
        rows={[
          ["Zone", z.primary_zone_name ? `${clean(z.primary_zone_name)} (${Math.round(z.overlap_pct ?? 0)}%)` : "Not zoned"],
          ...(z.zones.length > 1
            ? ([["Also", z.zones.slice(1).map((x) => `${clean(x.name)} (${Math.round(x.overlap_pct)}%)`).join(", ")]] as [string, React.ReactNode][])
            : []),
          ["Plan", "KUDA Master Plan 2041"],
        ]}
      />
      <p className="mt-2.5 text-[14px] text-muted">
        {z.permitted_uses ? `Permitted: ${clean(z.permitted_uses).replace(/^summarised placeholder: /, "")}. ` : ""}
        {clause && "page" in clause && clause.document_id
          ? `Source: ${clause.title}, page ${clause.page}.`
          : clause
            ? `Source: ${"note" in clause ? clause.note : ""}.`
            : ""}
      </p>
      {(isFallback(z.primary_zone_name) || synthetic.includes("zones")) && <SyntheticBadge label="Placeholder zone list" className="mt-3" />}
    </section>
  );

  return (
    <div className="flex flex-wrap items-start gap-6">
      <div className="flex min-w-0 flex-[999_1_640px] flex-col gap-6">
        {agriFirst && soilWater}
        <ValuationSection r={r} />

        <section className="card p-6" aria-labelledby="history-h">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="history-h" className="text-[26px]">
              Price history
            </h2>
            <span className="text-[13px] text-muted">Village median, ₹ per sq m</span>
          </div>
          <PriceHistory series={r.locality_trend.series} sales={r.price_history} project={anchor} />
          <p className="mt-2 text-[13px] text-muted">
            {r.price_history.length
              ? `Open circles: this parcel's ${r.price_history.length === 1 ? "recorded sale" : `${r.price_history.length} recorded sales`}.`
              : "This parcel has no recorded sale."}
            {r.locality_trend.series.some((p) => p.yoy_base_yr != null && p.yoy_base_yr < p.yr - 1) && " Years without sales are skipped."}
          </p>
        </section>

        <section className="card p-6" aria-labelledby="comps-h">
          <h2 id="comps-h" className="mb-3 text-[26px]">
            Comparable sales
          </h2>
          {r.comparables.length === 0 ? (
            <EmptyState title="No comparable sales" hint="No sale of the same land type within 10 km in the last 60 months." className="py-4" />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] border-collapse text-[14px]">
                  <thead>
                    <tr className="text-left text-[12px] text-muted">
                      <th className="border-b border-border px-2.5 py-2 font-medium">Parcel</th>
                      <th className="border-b border-border px-2.5 py-2 font-medium">Sold</th>
                      <th className="border-b border-border px-2.5 py-2 text-right font-medium">Distance</th>
                      <th className="border-b border-border px-2.5 py-2 text-right font-medium">Area, sq m</th>
                      <th className="border-b border-border px-2.5 py-2 text-right font-medium">₹ / sq m</th>
                      <th className="border-b border-border px-2.5 py-2 text-right font-medium">Adjusted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comps.map((c) => (
                      <tr key={c.parcel_id}>
                        <td className="border-b border-border px-2.5 py-2">
                          {survey(c)}, {clean(c.village)}
                        </td>
                        <td className="border-b border-border px-2.5 py-2 text-muted">{monthYear(c.registered_on)}</td>
                        <td className="num border-b border-border px-2.5 py-2 text-right">{dist(c.distance_m)}</td>
                        <td className="num border-b border-border px-2.5 py-2 text-right">{int(c.area_sqm)}</td>
                        <td className="num border-b border-border px-2.5 py-2 text-right">{inr(c.price_sqm)}</td>
                        <td className="num border-b border-border px-2.5 py-2 text-right">{inr(c.adjusted_price_sqm)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {r.comparables.length > 4 && (
                <button type="button" onClick={() => setAllComps(!allComps)} className="no-print mt-3 text-[14px] text-accent hover:text-accent-hover">
                  {allComps ? "Show fewer" : `Show all ${r.comparables.length} comparables`}
                </button>
              )}
            </>
          )}
        </section>

        <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-6">
          {zoning}
          {!agriFirst && soilWater}
        </div>
      </div>

      <aside className="flex min-w-0 flex-[1_1_320px] flex-col gap-6">
        <section className="card no-print p-5" aria-labelledby="ask-h">
          <h2 id="ask-h" className="mb-1 text-[22px]">
            Ask the master plan
          </h2>
          <p className="mb-3.5 text-[13px] text-muted">Answers come only from the government documents, with the page.</p>
          <ChatPanel parcelId={r.parcel_id} compact placeholder="Can I build a warehouse on this parcel?" />
        </section>

        <section className="card p-5" aria-labelledby="loc-h">
          <h2 id="loc-h" className="mb-2.5 text-[22px]">
            Location
          </h2>
          {projects.slice(0, 3).map((p) => (
            <div key={p.project_id} className="flex justify-between gap-3 border-t border-border py-2 text-[14px]">
              <span className="text-muted">
                {clean(p.name)}
                {p.status ? ` (${p.status.replace("_", " ")})` : ""}
              </span>
              <span className="num whitespace-nowrap">{dist(p.distance_m)}</span>
            </div>
          ))}
          <div className="flex justify-between gap-3 border-t border-border py-2 text-[14px]">
            <span className="text-muted">Nearest highway</span>
            <span className="num whitespace-nowrap">{dist(loc.distances_m.highway)}</span>
          </div>
          <div className="flex justify-between gap-3 border-t border-border py-2 text-[14px]">
            <span className="text-muted">Mandal, district</span>
            <span>
              {clean(loc.mandal)}, {clean(loc.district)}
            </span>
          </div>
        </section>

        <section className="card px-5 py-4 text-[13px] text-muted">
          Not legal or financial advice. Parcel boundaries, sales and soil values in this demo are synthetic
          {synthetic.length ? ` (synthetic here: ${synthetic.join(", ").replace(/_/g, " ")})` : ""}; roads, projects and
          documents are real where marked. Verify zoning with KUDA before buying. Valuation as of{" "}
          <span className="num">{r.valuation.as_of}</span>.
        </section>
      </aside>
    </div>
  );
}

function ReportSkeleton() {
  return (
    <div className="mx-auto max-w-page px-8 pb-14 pt-7" aria-busy="true" aria-label="Loading the report">
      <Skeleton className="mb-3 h-4 w-64" />
      <Skeleton className="mb-3 h-12 w-[28rem] max-w-full" />
      <div className="mb-6 flex gap-2">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-6 w-28" />
      </div>
      <div className="mb-7 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="tile p-4">
            <Skeleton className="mb-2 h-4 w-28" />
            <Skeleton className="mb-2 h-7 w-40" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </div>
      <SectionsSkeleton />
    </div>
  );
}

function SectionsSkeleton() {
  return (
    <div className="flex flex-wrap items-start gap-6" aria-busy="true">
      <div className="flex min-w-0 flex-[999_1_640px] flex-col gap-6">
        {[180, 260, 200].map((h) => (
          <div key={h} className="card p-6">
            <Skeleton className="mb-4 h-7 w-40" />
            <Skeleton style={{ height: h }} />
          </div>
        ))}
      </div>
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-6">
        {[200, 140].map((h) => (
          <div key={h} className="card p-5">
            <Skeleton className="mb-3 h-6 w-44" />
            <Skeleton style={{ height: h }} />
          </div>
        ))}
      </div>
    </div>
  );
}
