"use client";

import Link from "next/link";

import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import type { ScreenerPage, ScreenerRow, SortKey } from "@/lib/api";
import { clean, dist, inr, int, pct, pctFrac, survey } from "@/lib/format";
import { cn } from "@/lib/utils";

export const SORT_LABEL: Record<SortKey, string> = {
  cagr_5y: "5-year growth",
  price_sqm: "price per sq m",
  area_sqm: "area",
  nearest_active_project_m: "distance to an active project",
};

type Col = { key: string; label: string; right?: boolean; sort?: SortKey };
const COLS: Col[] = [
  { key: "parcel", label: "Parcel" },
  { key: "village", label: "Village" },
  { key: "zone", label: "Zone" },
  { key: "area", label: "Area, sq m", right: true, sort: "area_sqm" },
  { key: "price", label: "₹ / sq m", right: true, sort: "price_sqm" },
  { key: "vs", label: "vs median", right: true },
  { key: "growth", label: "5y growth", right: true, sort: "cagr_5y" },
  { key: "project", label: "Project", right: true, sort: "nearest_active_project_m" },
];

/** Results below the map (Map mockup): keyset "Load more", first/selected row tinted, sortable headers. */
export function ResultsTable({
  pages,
  status,
  error,
  refetch,
  hasNext,
  fetchingNext,
  loadMore,
  sort,
  order,
  onSort,
  selectedId,
  onRowClick,
  zoneNames,
  onReset,
}: {
  pages: ScreenerPage[] | undefined;
  status: "pending" | "error" | "success";
  error: unknown;
  refetch: () => void;
  hasNext: boolean;
  fetchingNext: boolean;
  loadMore: () => void;
  sort: SortKey;
  order: "asc" | "desc";
  onSort: (s: SortKey) => void;
  selectedId: number | null;
  onRowClick: (r: ScreenerRow) => void;
  zoneNames: Record<string, string>;
  onReset: () => void;
}) {
  const rows = pages?.flatMap((p) => p.items) ?? [];
  const total = pages?.[0]?.approx_total;
  const highlight = selectedId ?? rows[0]?.parcel_id;

  return (
    <section className="px-6 pb-8 pt-5" aria-label="Screener results">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-[22px]" data-testid="results-heading">
          {status === "success" ? `${int(total ?? 0)} ${total === 1 ? "parcel matches" : "parcels match"}` : "Parcels"}
        </h2>
        <span className="text-[13px] text-muted">
          Sorted by {SORT_LABEL[sort]}
          {order === "asc" ? ", lowest first" : ", highest first"}
        </span>
      </div>
      <div className="tile overflow-x-auto">
        {status === "pending" ? (
          <SkeletonRows rows={6} />
        ) : status === "error" ? (
          <ErrorState error={error} title="The screener could not load" onRetry={refetch} />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No parcels match these filters"
            hint="Widen the distance to a project or lower the growth threshold."
            action={
              <Button variant="outline" onClick={onReset}>
                Reset filters
              </Button>
            }
          />
        ) : (
          <table className="w-full min-w-[760px] border-collapse text-[14px]">
            <thead>
              <tr className="text-left text-[12px] text-muted">
                {COLS.map((c) => (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={c.sort === sort ? (order === "asc" ? "ascending" : "descending") : undefined}
                    className={cn("border-b border-border px-[14px] py-2.5 font-medium", c.right && "text-right")}
                  >
                    {c.sort ? (
                      <button
                        type="button"
                        onClick={() => onSort(c.sort!)}
                        className={cn("inline-flex items-center gap-1 hover:text-text", c.sort === sort && "text-text")}
                      >
                        {c.label}
                        {c.sort === sort && <span aria-hidden="true">{order === "asc" ? "↑" : "↓"}</span>}
                      </button>
                    ) : (
                      c.label
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.parcel_id}
                  onClick={() => onRowClick(r)}
                  className={cn("cursor-pointer hover:bg-bg", r.parcel_id === highlight && "bg-row-selected hover:bg-row-selected")}
                  data-testid="result-row"
                >
                  <td className="border-b border-border px-[14px] py-2.5">
                    <Link
                      href={`/parcels/${r.parcel_id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="font-medium no-underline"
                    >
                      {survey(r)}
                    </Link>
                  </td>
                  <td className="border-b border-border px-[14px] py-2.5">{clean(r.village_name)}</td>
                  <td className="border-b border-border px-[14px] py-2.5 text-muted">
                    {r.zone_code ? zoneNames[r.zone_code] ?? r.zone_code : "—"}
                  </td>
                  <td className="num border-b border-border px-[14px] py-2.5 text-right">{int(r.area_sqm)}</td>
                  <td className="num border-b border-border px-[14px] py-2.5 text-right">{inr(r.price_sqm)}</td>
                  {/* neutral on purpose: below median is good for a buyer (DESIGN.md) */}
                  <td className="num border-b border-border px-[14px] py-2.5 text-right">{pct(r.price_vs_median_pct)}</td>
                  <td
                    className={cn(
                      "num border-b border-border px-[14px] py-2.5 text-right",
                      r.cagr_5y == null ? "text-muted" : r.cagr_5y >= 0 ? "text-up" : "text-down",
                    )}
                  >
                    {pctFrac(r.cagr_5y)}
                  </td>
                  <td className="num border-b border-border px-[14px] py-2.5 text-right">{dist(r.nearest_active_project_m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {status === "success" && rows.length > 0 && (
        <div className="mt-4 text-center">
          {hasNext ? (
            <Button variant="outline" onClick={loadMore} disabled={fetchingNext} data-testid="load-more">
              {fetchingNext ? "Loading…" : "Load more"}
            </Button>
          ) : (
            <span className="text-[13px] text-muted">
              All {int(rows.length)} shown{rows.some((r) => r.cagr_5y == null) ? "; parcels without growth data are listed last" : ""}.
            </span>
          )}
        </div>
      )}
    </section>
  );
}

export const zoneNameMap = (zones: { zone_code: string; name: string }[] | undefined) =>
  Object.fromEntries((zones ?? []).map((z) => [z.zone_code, clean(z.name)]));
