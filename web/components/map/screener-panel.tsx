"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ToggleChip } from "@/components/ui/chip";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import type { LandType, ScreenerFilters } from "@/lib/api";
import { clean, int, LAND_TYPE_LABEL } from "@/lib/format";
import { useScreenerCount, useScreenerOptions } from "@/lib/queries";

/** null = the slider sits at its "Any" end = no filter. */
export type FormState = {
  landType: LandType | null;
  zones: string[];
  projectKm: number | null;
  growthPct: number | null;
  vsMedianPct: number | null; // -50..+45 in steps of 5
  excludeOverExploited: boolean;
};
export const DEFAULT_FORM: FormState = {
  landType: null,
  zones: [],
  projectKm: null,
  growthPct: null,
  vsMedianPct: null,
  excludeOverExploited: false,
};

export function toFilters(f: FormState): ScreenerFilters {
  const out: ScreenerFilters = {};
  if (f.landType) out.land_type = f.landType;
  if (f.zones.length) out.zone_code = [...f.zones].sort();
  if (f.projectKm != null) out.max_active_project_m = Math.round(f.projectKm * 1000);
  if (f.growthPct != null) out.min_cagr_5y = f.growthPct / 100;
  if (f.vsMedianPct != null) out.max_price_vs_median_pct = f.vsMedianPct;
  if (f.excludeOverExploited) out.exclude_gw = ["over_exploited"];
  return out;
}

/** Slider ends from the data (/screener/options ranges), so every position can change the result. */
function bounds(r: Record<string, number> | undefined) {
  const projMaxKm = Math.max(1, Math.ceil(((r?.active_project_m_max ?? 10000) / 1000) * 2) / 2);
  return {
    projMaxKm,
    projStep: projMaxKm <= 3 ? 0.1 : 0.5,
    growthMax: Math.max(5, Math.ceil((r?.cagr_5y_max ?? 0.25) * 100)),
  };
}
const km = (v: number) => (v < 1 ? `${Math.round(v * 1000)} m` : `${Number(v.toFixed(1))} km`);

function useDebounced<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

function Row({ label, value, children }: { label: string; value: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <div className="mb-[14px] flex justify-between gap-3 text-[13px] text-muted">
        <span>{label}</span>
        <span className="num text-text">{value}</span>
      </div>
      {children}
    </div>
  );
}

/**
 * Left screener panel (Map mockup, FR-4). Edits are pending until "Show N parcels"; N is a live count of the
 * pending filters (a limit-1 screener call, debounced).
 */
export function ScreenerPanel({
  form,
  setForm,
  onApply,
  onReset,
  dirty,
}: {
  form: FormState;
  setForm: (f: FormState) => void;
  onApply: () => void;
  onReset: () => void;
  dirty: boolean;
}) {
  const opts = useScreenerOptions();
  const pending = useDebounced(toFilters(form), 300);
  const count = useScreenerCount(pending);
  const set = (p: Partial<FormState>) => setForm({ ...form, ...p });
  const bd = bounds(opts.data?.ranges);
  const zoneName = (code: string) => clean(opts.data?.zones.find((z) => z.zone_code === code)?.name ?? code);

  return (
    <aside
      id="screener"
      className="box-border w-full border-border bg-surface px-5 pb-7 pt-5 min-[900px]:w-[320px] min-[900px]:shrink-0 min-[900px]:border-r"
      aria-label="Screener"
    >
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-[22px]">Screener</h2>
        <button type="button" onClick={onReset} className="text-[13px] text-accent hover:text-accent-hover">
          Reset
        </button>
      </div>

      <div className="mb-2 text-[13px] text-muted">Land type</div>
      <div className="mb-5 flex flex-wrap gap-1.5">
        {(["urban_plot", "peri_urban", "agricultural"] as LandType[]).map((t) => (
          <ToggleChip key={t} selected={form.landType === t} onClick={() => set({ landType: form.landType === t ? null : t })}>
            {LAND_TYPE_LABEL[t]}
          </ToggleChip>
        ))}
      </div>

      <div className="mb-1.5 text-[13px] text-muted" id="zone-label">
        Master plan zone
      </div>
      <Popover>
        <PopoverTrigger
          aria-labelledby="zone-label"
          className="mb-5 flex w-full items-center justify-between gap-2 rounded-lg border border-border px-3 py-[9px] text-left text-[15px]"
        >
          <span className="truncate">{form.zones.length ? form.zones.map(zoneName).join(", ") : "Any zone"}</span>
          <span className="text-muted" aria-hidden="true">
            ▾
          </span>
        </PopoverTrigger>
        <PopoverContent className="w-[280px]">
          {opts.isPending ? (
            <div className="p-2 text-[13px] text-muted">Loading zones…</div>
          ) : opts.isError ? (
            <div className="p-2 text-[13px] text-down">Zones could not load. {opts.error.message}</div>
          ) : (
            <ul className="flex flex-col">
              {opts.data.zones.map((z) => {
                const on = form.zones.includes(z.zone_code);
                return (
                  <li key={z.zone_code}>
                    <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[14px] hover:bg-bg">
                      <Checkbox
                        checked={on}
                        onCheckedChange={() =>
                          set({ zones: on ? form.zones.filter((c) => c !== z.zone_code) : [...form.zones, z.zone_code] })
                        }
                      />
                      <span>{clean(z.name)}</span>
                      <span className="num ml-auto text-[12px] text-muted">{z.zone_code}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </PopoverContent>
      </Popover>

      <Row label="Distance to an active project" value={form.projectKm == null ? "Any" : `within ${km(form.projectKm)}`}>
        <Slider
          aria-label="Distance to an active project, km"
          min={bd.projStep}
          max={bd.projMaxKm}
          step={bd.projStep}
          value={[form.projectKm ?? bd.projMaxKm]}
          onValueChange={([v]) => set({ projectKm: v >= bd.projMaxKm ? null : Number(v.toFixed(1)) })}
        />
      </Row>
      <Row label="5-year growth, at least" value={form.growthPct == null ? "Any" : `${form.growthPct}% a year`}>
        <Slider
          aria-label="5-year growth per year, at least, percent"
          min={0}
          max={bd.growthMax}
          step={1}
          value={[form.growthPct ?? 0]}
          onValueChange={([v]) => set({ growthPct: v <= 0 ? null : v })}
        />
      </Row>
      <Row
        label="Price vs village median"
        value={
          form.vsMedianPct == null
            ? "Any"
            : `below ${form.vsMedianPct > 0 ? "+" : form.vsMedianPct < 0 ? "\u2212" : ""}${Math.abs(form.vsMedianPct)}%`
        }
      >
        <Slider
          aria-label="Price versus village median, at most, percent"
          min={-50}
          max={50}
          step={5}
          value={[form.vsMedianPct ?? 50]}
          onValueChange={([v]) => set({ vsMedianPct: v >= 50 ? null : v })}
        />
      </Row>

      <label className="mb-6 flex items-center gap-2 text-[14px]">
        <Checkbox
          checked={form.excludeOverExploited}
          onCheckedChange={(c) => set({ excludeOverExploited: c === true })}
        />
        Exclude over-exploited groundwater
      </label>

      <Button variant="primary" size="block" onClick={onApply} data-testid="apply-filters">
        {count.isError
          ? "Show parcels"
          : count.data == null
            ? "Counting…"
            : `Show ${int(count.data)} ${count.data === 1 ? "parcel" : "parcels"}`}
      </Button>
      {dirty && <p className="mt-2 text-center text-[12px] text-muted">Filters changed: press to update the map and list.</p>}
      <p className="mt-4 text-[12px] text-muted">Synthetic data: villages, roads, projects, zones, parcels and prices. Parcels cover the urban core and growth corridors.</p>
    </aside>
  );
}
