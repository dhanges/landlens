"use client";

import Link from "next/link";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import type { ParcelSummary } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { area, clean, dist, inr, LAND_TYPE_LABEL, pctFrac, survey } from "@/lib/format";
import { HEAT_LEGEND, OVERLAY_LABELS, type Overlay } from "@/lib/map/style";
import { cn } from "@/lib/utils";

export function LayersPanel({
  overlays,
  setOverlays,
}: {
  overlays: Record<Overlay, boolean>;
  setOverlays: (o: Record<Overlay, boolean>) => void;
}) {
  return (
    <div className="tile absolute right-4 top-4 z-10 flex flex-col gap-1.5 px-[14px] py-3 text-[13px]">
      <div className="mb-0.5 font-medium">Layers</div>
      {(Object.keys(OVERLAY_LABELS) as Overlay[]).map((o) => (
        <label key={o} className="flex cursor-pointer items-center gap-2">
          <Checkbox checked={overlays[o]} onCheckedChange={(c) => setOverlays({ ...overlays, [o]: c === true })} />
          {OVERLAY_LABELS[o]}
        </label>
      ))}
    </div>
  );
}

export function Legend({ zoomedOut }: { zoomedOut: boolean }) {
  return (
    <div className="tile absolute bottom-4 left-4 z-10 px-[14px] py-2.5 text-[12px] text-muted">
      <div className="mb-1.5">{zoomedOut ? "Village median price per sq m (zoom in for parcels)" : "Price per sq m vs village median"}</div>
      <div className="flex items-center gap-1">
        {HEAT_LEGEND.map((c) => (
          <span key={c} className="h-2.5 w-7 rounded-[2px]" style={{ background: c }} />
        ))}
        <span className="ml-1.5">{zoomedOut ? "lower · middle · higher" : "below · near · above"}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5">
        <span className="w-7 border-t-[1.5px] border-dashed border-muted" />
        <span>parcel coverage</span>
        <span className="ml-2 w-7 border-t-2 border-dashed border-accent" />
        <span>projects</span>
      </div>
    </div>
  );
}

function CardRow({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className="flex justify-between border-t border-border py-1.5 text-[13px]">
      <span className="text-muted">{label}</span>
      <span className={cn("num", className)}>{children}</span>
    </div>
  );
}

export type CardState =
  | { kind: "loading" }
  | { kind: "parcel"; summary: ParcelSummary }
  | { kind: "village"; village_id: number; name: string; median_price_sqm: number | null }
  | { kind: "error"; error: unknown };

const MISS_TITLE: Record<string, string> = {
  outside_coverage: "Outside the KUDA area",
  outside_parcel_window: "No parcel data here yet",
  no_parcel_at_point: "No parcel at this point",
};

/** Floating clicked-parcel card (Map mockup): three mono rows and "Unlock full report · 1 credit". */
export function ParcelCard({
  state,
  pos,
  onClose,
  onZoomIn,
}: {
  state: CardState;
  pos: { x: number; y: number } | null;
  onClose: () => void;
  onZoomIn: () => void;
}) {
  const style = pos ? { left: pos.x, top: pos.y } : { left: 16, top: 16 };
  return (
    <div
      className="card absolute z-20 w-[300px] p-4"
      style={style}
      role="dialog"
      aria-label="Parcel summary"
      data-testid="parcel-card"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-bg hover:text-text"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
      {state.kind === "loading" && (
        <div className="flex flex-col gap-2" aria-busy="true">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-56" />
          <Skeleton className="mt-2 h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="mt-2 h-10 w-full" />
        </div>
      )}
      {state.kind === "error" &&
        (state.error instanceof ApiError && MISS_TITLE[state.error.code] ? (
          <div className="pr-6">
            <div className="font-serif text-[20px] font-medium">{MISS_TITLE[state.error.code]}</div>
            <p className="mt-1 text-[13px] text-muted">{state.error.message}</p>
          </div>
        ) : (
          <ErrorState error={state.error} title="Could not load this parcel" className="px-0 py-2" />
        ))}
      {state.kind === "village" && (
        <div>
          <div className="pr-6 font-serif text-[20px] font-medium">{clean(state.name)}</div>
          <div className="mb-3 mt-0.5 text-[13px] text-muted">Village · zoom in to see parcels</div>
          <CardRow label="Village median">{state.median_price_sqm == null ? "No sales" : `${inr(state.median_price_sqm)} /sq m`}</CardRow>
          <div className="mt-3 flex gap-2">
            <Button variant="outline" size="sm" onClick={onZoomIn} className="flex-1">
              Zoom to parcels
            </Button>
            <Button asChild variant="outline" size="sm" className="flex-1">
              <Link href={`/trends?village=${state.village_id}`}>Price trend</Link>
            </Button>
          </div>
        </div>
      )}
      {state.kind === "parcel" && <SummaryBody s={state.summary} />}
    </div>
  );
}

function SummaryBody({ s }: { s: ParcelSummary }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 pr-6">
        <span className="font-serif text-[20px] font-medium">Survey {survey(s)}</span>
        <Chip tone="tint" className="px-2 py-0.5 text-[12px]">
          {LAND_TYPE_LABEL[s.land_type]}
        </Chip>
      </div>
      <div className="mb-3 mt-0.5 text-[13px] text-muted">
        {clean(s.village)} · {area(s.area_sqm)}
        {s.zone_name ? ` · ${clean(s.zone_name)} zone` : ""}
      </div>
      <CardRow label="Village median">{s.village_median_sqm == null ? "No recent sales" : `${inr(s.village_median_sqm)} /sq m`}</CardRow>
      <CardRow label="5-year growth" className={s.cagr_5y == null ? "text-muted" : s.cagr_5y >= 0 ? "text-up" : "text-down"}>
        {s.cagr_5y == null ? "Not enough sales" : `${pctFrac(s.cagr_5y)} a year`}
      </CardRow>
      <CardRow label="Nearest active project">{dist(s.nearest_active_project_m)}</CardRow>
      <Button asChild variant="primary" className="mt-3 w-full" data-testid="card-cta">
        <Link href={`/parcels/${s.parcel_id}`}>{s.unlocked ? "Open full report" : "Unlock full report · 1 credit"}</Link>
      </Button>
      {s.source === "synthetic" && <p className="mt-2 text-center text-[11px] text-muted">Synthetic parcel and prices</p>}
    </div>
  );
}
