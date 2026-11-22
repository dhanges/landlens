"use client";

import type { GeoJSONSource, Map as MLMap, MapMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { loadMaplibre } from "@/lib/map/maplibre";
import {
  buildStyle,
  DEFAULT_VIEW,
  EMPTY,
  OVERLAY_LAYERS,
  PARCEL_MIN_ZOOM,
  type Overlay,
  type StyleData,
} from "@/lib/map/style";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export type MapClick =
  | { kind: "parcel"; lngLat: [number, number] }
  | {
      kind: "village";
      lngLat: [number, number];
      village_id: number;
      name: string;
      median_price_sqm: number | null;
    };

export type ParcelMapHandle = {
  flyTo: (lon: number, lat: number, zoom?: number) => void;
  fitPoints: (pts: [number, number][]) => void;
  project: (lngLat: [number, number]) => { x: number; y: number } | null;
  getZoom: () => number;
};

type Props = {
  overlays: Record<Overlay, boolean>;
  results: GeoJSON.FeatureCollection;
  selected: GeoJSON.Feature | null;
  onClick: (c: MapClick) => void;
  onMove?: () => void;
  className?: string;
};

/**
 * MapLibre map with the LandLens topo style (lib/map/style.ts). Parcels from z14, villages below. A theme flip
 * rebuilds the style from the tokens and applies it with setStyle(diff), so tiles stay loaded. Clicks report a
 * point (parcel zoom) or the village under the cursor (below z14); the page resolves them through the API.
 */
export const ParcelMap = forwardRef<ParcelMapHandle, Props>(function ParcelMap(
  { overlays, results, selected, onClick, onMove, className },
  ref,
) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const { theme } = useTheme();
  const latest = useRef({ overlays, results, selected, onClick, onMove });
  latest.current = { overlays, results, selected, onClick, onMove };

  const styleData = (): StyleData => {
    const s = latest.current.selected;
    const centroid = s?.properties?.centroid as [number, number] | undefined;
    return {
      overlays: latest.current.overlays,
      results: latest.current.results,
      selected: s ?? EMPTY,
      selectedPoint: centroid
        ? { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: centroid } }
        : EMPTY,
    };
  };

  useImperativeHandle(ref, () => ({
    flyTo: (lon, lat, zoom) => {
      const m = map.current;
      if (!m) return;
      m.flyTo({ center: [lon, lat], zoom: zoom ?? Math.max(m.getZoom(), 16), speed: 1.6 });
    },
    fitPoints: (pts) => {
      const m = map.current;
      if (!m || pts.length === 0) return;
      if (pts.length === 1) {
        m.flyTo({ center: pts[0], zoom: 16 });
        return;
      }
      const lons = pts.map((p) => p[0]);
      const lats = pts.map((p) => p[1]);
      m.fitBounds(
        [
          [Math.min(...lons), Math.min(...lats)],
          [Math.max(...lons), Math.max(...lats)],
        ],
        { padding: 60, maxZoom: 16, duration: 900 },
      );
    },
    getZoom: () => map.current?.getZoom() ?? 0,
    project: (lngLat) => {
      const m = map.current;
      if (!m) return null;
      const p = m.project(lngLat);
      return { x: p.x, y: p.y };
    },
  }));

  // create once
  useEffect(() => {
    let cancelled = false;
    let instance: MLMap | null = null;
    loadMaplibre()
      .then((ml) => {
        if (cancelled || !el.current) return;
        try {
          instance = new ml.Map({
            container: el.current,
            style: buildStyle(window.location.origin, styleData()),
            center: DEFAULT_VIEW.center,
            zoom: DEFAULT_VIEW.zoom,
            minZoom: 9,
            maxZoom: 19,
            attributionControl: { compact: true },
            dragRotate: false,
            pitchWithRotate: false,
          });
        } catch (e) {
          setFailed((e as Error).message || "WebGL is not available.");
          return;
        }
        map.current = instance;
        // handle for browser checks (journey scripts wait on map idle and read the camera)
        (window as unknown as { __landlensMap?: MLMap }).__landlensMap = instance;
        instance.addControl(new ml.NavigationControl({ showCompass: false }), "bottom-right");
        instance.addControl(new ml.ScaleControl({ unit: "metric" }), "bottom-right");
        instance.on("load", () => setReady(true));
        instance.on("move", () => latest.current.onMove?.());
        const hoverLayers = ["ll-parcels-fill", "ll-villages-fill"];
        for (const l of hoverLayers) {
          instance.on("mouseenter", l, () => (instance!.getCanvas().style.cursor = "pointer"));
          instance.on("mouseleave", l, () => (instance!.getCanvas().style.cursor = ""));
        }
        instance.on("click", (e: MapMouseEvent) => {
          const m = instance!;
          const lngLat: [number, number] = [e.lngLat.lng, e.lngLat.lat];
          if (m.getZoom() < PARCEL_MIN_ZOOM) {
            const v = m.queryRenderedFeatures(e.point, { layers: ["ll-villages-fill"] })[0];
            if (v) {
              const p = v.properties as { village_id: number; name: string; median_price_sqm?: number | null };
              latest.current.onClick({
                kind: "village",
                lngLat,
                village_id: Number(p.village_id),
                name: String(p.name),
                median_price_sqm: p.median_price_sqm == null ? null : Number(p.median_price_sqm),
              });
            }
            return;
          }
          latest.current.onClick({ kind: "parcel", lngLat });
        });
      })
      .catch((e) => setFailed((e as Error).message || "The map could not load."));
    return () => {
      cancelled = true;
      instance?.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // theme flip: same sources, new colours
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    m.setStyle(buildStyle(window.location.origin, styleData()), { diff: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    for (const [o, layers] of Object.entries(OVERLAY_LAYERS) as [Overlay, string[]][]) {
      for (const id of layers) if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", overlays[o] ? "visible" : "none");
    }
  }, [overlays, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const d = styleData();
    (m.getSource("results") as GeoJSONSource | undefined)?.setData(d.results);
    (m.getSource("selected") as GeoJSONSource | undefined)?.setData(d.selected);
    (m.getSource("selected-point") as GeoJSONSource | undefined)?.setData(d.selectedPoint);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results, selected, ready]);

  return (
    <div className={cn("relative", className)}>
      <div ref={el} className="h-full w-full" data-testid="map" />
      {!ready && !failed && (
        <div className="absolute inset-0 flex items-center justify-center bg-bg" aria-busy="true">
          <Skeleton className="absolute inset-0 rounded-none" />
          <span className="relative text-[13px] text-muted">Loading the map…</span>
        </div>
      )}
      {failed && (
        <div role="alert" className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-bg p-6 text-center">
          <h3 className="text-[22px]">The map could not start</h3>
          <p className="max-w-sm text-[14px] text-muted">
            Your browser did not provide WebGL ({failed}). The screener table below still works.
          </p>
        </div>
      )}
    </div>
  );
});
