"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LayersPanel, Legend, ParcelCard, type CardState } from "@/components/map/map-panels";
import { ParcelMap, type MapClick, type ParcelMapHandle } from "@/components/map/parcel-map";
import { ResultsTable, zoneNameMap } from "@/components/map/results-table";
import { DEFAULT_FORM, ScreenerPanel, toFilters, type FormState } from "@/components/map/screener-panel";
import * as api from "@/lib/api";
import { DEFAULT_OVERLAYS, PARCEL_MIN_ZOOM, type Overlay } from "@/lib/map/style";
import { keys, useScreener, useScreenerOptions } from "@/lib/queries";

const DEFAULT_ORDER: Record<api.SortKey, "asc" | "desc"> = {
  cagr_5y: "desc",
  price_sqm: "asc",
  area_sqm: "desc",
  nearest_active_project_m: "asc",
};
const CARD_W = 300;
const CARD_H = 270;

/** Map + screener page (J1, J2 step 1): screener panel, map with floating panels, results table. */
export function MapScreener() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const mapRef = useRef<ParcelMapHandle>(null);
  const wrap = useRef<HTMLDivElement>(null);

  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [applied, setApplied] = useState<api.ScreenerFilters>({});
  const [sort, setSort] = useState<api.SortKey>("cagr_5y");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [overlays, setOverlays] = useState<Record<Overlay, boolean>>(DEFAULT_OVERLAYS);
  const [card, setCard] = useState<CardState | null>(null);
  const [cardAt, setCardAt] = useState<[number, number] | null>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [selected, setSelected] = useState<api.ParcelSummary | null>(null);
  const [zoomedOut, setZoomedOut] = useState(true);
  const fitNext = useRef(false);
  const clickSeq = useRef(0);

  const opts = useScreenerOptions();
  const zoneNames = useMemo(() => zoneNameMap(opts.data?.zones), [opts.data]);
  const q = useScreener(applied, sort, order);
  const rows = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data]);
  const dirty = JSON.stringify(toFilters(form)) !== JSON.stringify(applied);

  const results = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: rows
        .filter((r) => r.lat != null && r.lon != null)
        .map((r) => ({
          type: "Feature",
          properties: { parcel_id: r.parcel_id, selected: r.parcel_id === selected?.parcel_id },
          geometry: { type: "Point", coordinates: [r.lon!, r.lat!] },
        })),
    }),
    [rows, selected],
  );
  const selectedFeature = useMemo<GeoJSON.Feature | null>(
    () =>
      selected
        ? { type: "Feature", properties: { centroid: [selected.lon, selected.lat] }, geometry: selected.geometry }
        : null,
    [selected],
  );

  // keep the card next to its point while the map moves
  const place = useCallback(() => {
    const m = mapRef.current;
    const box = wrap.current?.getBoundingClientRect();
    if (!m || !cardAt || !box) return setPos(null);
    const p = m.project(cardAt);
    if (!p) return;
    let x = p.x + 18;
    let y = p.y - 40;
    if (x + CARD_W > box.width - 12) x = p.x - CARD_W - 18;
    x = Math.max(12, Math.min(x, box.width - CARD_W - 12));
    y = Math.max(12, Math.min(y, box.height - CARD_H - 12));
    setPos({ x, y });
  }, [cardAt]);
  useEffect(place, [place]);

  const onMove = useCallback(() => {
    requestAnimationFrame(place);
    const m = mapRef.current;
    if (m) setZoomedOut(m.getZoom() < PARCEL_MIN_ZOOM);
  }, [place]);

  const showParcel = useCallback(
    async (load: () => Promise<api.ParcelSummary>, at: [number, number]) => {
      const seq = ++clickSeq.current;
      setCardAt(at);
      setCard({ kind: "loading" });
      try {
        const s = await load();
        if (seq !== clickSeq.current) return;
        qc.setQueryData(keys.summary(s.parcel_id), s);
        setSelected(s);
        setCard({ kind: "parcel", summary: s });
      } catch (error) {
        if (seq !== clickSeq.current) return;
        setCard({ kind: "error", error });
      }
    },
    [qc],
  );

  const onMapClick = useCallback(
    (c: MapClick) => {
      if (c.kind === "village") {
        clickSeq.current++;
        setCardAt(c.lngLat);
        setCard({ kind: "village", village_id: c.village_id, name: c.name, median_price_sqm: c.median_price_sqm });
        return;
      }
      showParcel(() => api.parcelAt(c.lngLat[1], c.lngLat[0]), c.lngLat);
    },
    [showParcel],
  );

  // header search: /map?lat=..&lon=..&village=ID | &parcel=ID
  useEffect(() => {
    const lat = Number(params.get("lat"));
    const lon = Number(params.get("lon"));
    const parcel = Number(params.get("parcel"));
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || (!lat && !lon)) return;
    const t = setTimeout(() => {
      if (parcel) {
        mapRef.current?.flyTo(lon, lat, 17);
        showParcel(() => api.parcelSummary(parcel), [lon, lat]);
      } else {
        mapRef.current?.flyTo(lon, lat, 14.5);
        setCard(null);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [params, showParcel]);

  // after "Show N parcels": frame the first page of results
  useEffect(() => {
    if (!fitNext.current || q.status !== "success") return;
    fitNext.current = false;
    const pts = rows.filter((r) => r.lat != null).map((r) => [r.lon!, r.lat!] as [number, number]);
    if (pts.length) mapRef.current?.fitPoints(pts);
  }, [q.status, rows]);

  const apply = () => {
    fitNext.current = true;
    setApplied(toFilters(form));
  };
  const reset = () => {
    setForm(DEFAULT_FORM);
    setApplied({});
  };
  const onSort = (s: api.SortKey) => {
    if (s === sort) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(s);
      setOrder(DEFAULT_ORDER[s]);
    }
  };
  const onRowClick = (r: api.ScreenerRow) => {
    if (r.lat == null || r.lon == null) return;
    mapRef.current?.flyTo(r.lon, r.lat, 17);
    showParcel(() => api.parcelSummary(r.parcel_id), [r.lon, r.lat]);
    wrap.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <div className="flex flex-1 flex-col items-stretch min-[900px]:flex-row">
      <ScreenerPanel form={form} setForm={setForm} onApply={apply} onReset={reset} dirty={dirty} />
      <main className="flex min-w-0 flex-1 flex-col">
        <div ref={wrap} className="relative h-[560px] overflow-hidden border-b border-border bg-[var(--map-land)]">
          <ParcelMap
            ref={mapRef}
            className="absolute inset-0"
            overlays={overlays}
            results={results}
            selected={selectedFeature}
            onClick={onMapClick}
            onMove={onMove}
          />
          <LayersPanel overlays={overlays} setOverlays={setOverlays} />
          <Legend zoomedOut={zoomedOut} />
          {card && (
            <ParcelCard
              state={card}
              pos={pos}
              onClose={() => {
                clickSeq.current++;
                setCard(null);
                setCardAt(null);
                setSelected(null);
              }}
              onZoomIn={() => cardAt && mapRef.current?.flyTo(cardAt[0], cardAt[1], 15)}
            />
          )}
        </div>
        <ResultsTable
          pages={q.data?.pages}
          status={q.status}
          error={q.error}
          refetch={() => q.refetch()}
          hasNext={!!q.hasNextPage}
          fetchingNext={q.isFetchingNextPage}
          loadMore={() => q.fetchNextPage()}
          sort={sort}
          order={order}
          onSort={onSort}
          selectedId={selected?.parcel_id ?? null}
          onRowClick={onRowClick}
          zoneNames={zoneNames}
          onReset={reset}
        />
      </main>
    </div>
  );
}
