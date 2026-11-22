/**
 * MapLibre topo style (web/DESIGN.md "Map style"). Base: OpenFreeMap's free OpenMapTiles vector tiles (no key),
 * restyled from the DESIGN.md map table instead of loading a ready-made style, so every colour comes from the
 * design tokens. Ours on top: Martin sources from migrations 012/014 (parcels from z14, villages below).
 *
 * Colours are read from CSS variables at call time (cssVar), so buildStyle() after a theme flip returns the dark
 * or light variant, and map.setStyle(..., { diff: true }) only repaints. Labels use Schibsted Grotesk through
 * MapLibre 6 `font-faces` (public/fonts/), with OpenFreeMap glyphs as the fallback for uncovered characters.
 */
import type {
  ExpressionSpecification,
  LayerSpecification,
  SourceSpecification,
  StyleSpecification,
} from "@maplibre/maplibre-gl-style-spec";

import { cssVar } from "@/lib/theme";

export const OPENFREEMAP = "https://tiles.openfreemap.org/planet";
export const PARCEL_MIN_ZOOM = 14;
/** Warangal: centre of the SF1 parcel window (parcel_coverage). */
export const DEFAULT_VIEW = { center: [79.5414, 17.9693] as [number, number], zoom: 12 };

export type Overlay = "parcels" | "projects" | "zones" | "water" | "roads";
export const OVERLAY_LABELS: Record<Overlay, string> = {
  parcels: "Parcels",
  projects: "Development projects",
  zones: "Master plan zones",
  water: "Water bodies",
  roads: "Roads",
};
export const DEFAULT_OVERLAYS: Record<Overlay, boolean> = {
  parcels: true,
  projects: true,
  zones: false,
  water: false,
  roads: false,
};

/** Which of our layer ids each overlay toggle shows or hides. */
export const OVERLAY_LAYERS: Record<Overlay, string[]> = {
  parcels: ["ll-villages-fill", "ll-villages-line", "ll-villages-label", "ll-parcels-fill", "ll-parcels-line"],
  projects: ["ll-projects-fill", "ll-projects-line", "ll-projects-label"],
  zones: ["ll-zones-fill", "ll-zones-line", "ll-zones-label"],
  water: ["ll-water-fill", "ll-water-line"],
  roads: ["ll-roads-casing", "ll-roads"],
};

type Geo = GeoJSON.FeatureCollection | GeoJSON.Feature;
export const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

const FONT = ["Schibsted Grotesk Regular"];
const FONT_ITALIC = ["Schibsted Grotesk Italic"];
const NAME: ExpressionSpecification = ["coalesce", ["get", "name:latin"], ["get", "name_en"], ["get", "name"]];
/** "[fallback] Mamnoor airport" -> "Mamnoor airport" (the fallback marker is shown as a badge, not in labels). */
const CLEAN_NAME: ExpressionSpecification = [
  "case",
  ["==", ["slice", ["get", "name"], 0, 11], "[fallback] "],
  ["slice", ["get", "name"], 11],
  ["get", "name"],
];

function colours() {
  const c = (n: string) => cssVar(`--${n}`);
  return {
    land: c("map-land"),
    farmland: c("map-farmland"),
    grass: c("map-grass"),
    forest: c("map-forest"),
    water: c("map-water"),
    waterLine: c("map-water-line"),
    road: c("map-road"),
    roadCasing: c("map-road-casing"),
    path: c("map-path"),
    building: c("map-building"),
    buildingLine: c("map-building-line"),
    label: c("map-label"),
    halo: c("map-halo"),
    surface: c("surface"),
    border: c("border"),
    muted: c("muted"),
    primary: c("primary"),
    accent: c("accent"),
    down: c("down"),
    tint: c("tint"),
    heat1: c("heat-1"),
    heat2: c("heat-2"),
    heat3: c("heat-3"),
  };
}

const zoomWidth = (stops: [number, number][]): ExpressionSpecification =>
  ["interpolate", ["exponential", 1.5], ["zoom"], ...stops.flat()] as unknown as ExpressionSpecification;

function baseLayers(k: ReturnType<typeof colours>): LayerSpecification[] {
  const omt = { source: "omt" } as const;
  const roadClass = (classes: string[]): ExpressionSpecification => [
    "all",
    ["match", ["geometry-type"], ["LineString", "MultiLineString"], true, false],
    ["match", ["get", "class"], classes, true, false],
  ];
  const major = ["motorway", "trunk", "primary"];
  const mid = ["secondary", "tertiary"];
  const minor = ["minor", "service", "street", "street_limited"];
  return [
    { id: "background", type: "background", paint: { "background-color": k.land } },
    {
      id: "landcover-farmland",
      type: "fill",
      ...omt,
      "source-layer": "landcover",
      filter: ["==", ["get", "class"], "farmland"],
      paint: { "fill-color": k.farmland },
    },
    {
      id: "landcover-grass",
      type: "fill",
      ...omt,
      "source-layer": "landcover",
      filter: ["match", ["get", "class"], ["grass", "wetland", "scrub"], true, false],
      paint: { "fill-color": k.grass },
    },
    {
      id: "park",
      type: "fill",
      ...omt,
      "source-layer": "park",
      paint: { "fill-color": k.grass, "fill-opacity": 0.8 },
    },
    {
      id: "landcover-wood",
      type: "fill",
      ...omt,
      "source-layer": "landcover",
      filter: ["match", ["get", "class"], ["wood", "forest"], true, false],
      paint: { "fill-color": k.forest },
    },
    {
      id: "waterway",
      type: "line",
      ...omt,
      "source-layer": "waterway",
      filter: ["!=", ["get", "brunnel"], "tunnel"],
      paint: {
        "line-color": k.waterLine,
        "line-width": zoomWidth([
          [10, 0.6],
          [16, 2.5],
        ]),
      },
    },
    {
      id: "water",
      type: "fill",
      ...omt,
      "source-layer": "water",
      filter: ["!=", ["get", "brunnel"], "tunnel"],
      paint: { "fill-color": k.water },
    },
    {
      id: "water-outline",
      type: "line",
      ...omt,
      "source-layer": "water",
      filter: ["!=", ["get", "brunnel"], "tunnel"],
      paint: { "line-color": k.waterLine, "line-width": 1.2 },
    },
    {
      id: "building",
      type: "fill",
      ...omt,
      "source-layer": "building",
      minzoom: 13,
      paint: { "fill-color": k.building, "fill-outline-color": k.buildingLine },
    },
    {
      id: "road-path",
      type: "line",
      ...omt,
      "source-layer": "transportation",
      minzoom: 12,
      filter: roadClass(["track", "path", "pedestrian"]),
      layout: { "line-cap": "round" },
      paint: { "line-color": k.path, "line-width": 2.5, "line-dasharray": [7 / 2.5, 5 / 2.5] },
    },
    {
      id: "road-minor-casing",
      type: "line",
      ...omt,
      "source-layer": "transportation",
      minzoom: 12,
      filter: roadClass(minor),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": k.roadCasing,
        "line-width": zoomWidth([
          [12, 1.5],
          [16, 8],
        ]),
      },
    },
    {
      id: "road-mid-casing",
      type: "line",
      ...omt,
      "source-layer": "transportation",
      filter: roadClass(mid),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": k.roadCasing,
        "line-width": zoomWidth([
          [9, 1.5],
          [16, 13],
        ]),
      },
    },
    {
      id: "road-major-casing",
      type: "line",
      ...omt,
      "source-layer": "transportation",
      filter: roadClass(major),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": k.roadCasing,
        "line-width": zoomWidth([
          [7, 2],
          [16, 18],
        ]),
      },
    },
    {
      id: "road-minor",
      type: "line",
      ...omt,
      "source-layer": "transportation",
      minzoom: 12,
      filter: roadClass(minor),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": k.road,
        "line-width": zoomWidth([
          [12, 0.8],
          [16, 6],
        ]),
      },
    },
    {
      id: "road-mid",
      type: "line",
      ...omt,
      "source-layer": "transportation",
      filter: roadClass(mid),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": k.road,
        "line-width": zoomWidth([
          [9, 0.8],
          [16, 10],
        ]),
      },
    },
    {
      id: "road-major",
      type: "line",
      ...omt,
      "source-layer": "transportation",
      filter: roadClass(major),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": k.road,
        "line-width": zoomWidth([
          [7, 1.2],
          [16, 14],
        ]),
      },
    },
  ];
}

function labelLayers(k: ReturnType<typeof colours>): LayerSpecification[] {
  const halo = { "text-color": k.label, "text-halo-color": k.halo, "text-halo-width": 1.5 };
  return [
    {
      id: "label-water",
      type: "symbol",
      source: "omt",
      "source-layer": "water_name",
      layout: { "text-field": NAME, "text-font": FONT_ITALIC, "text-size": 13 },
      paint: { ...halo, "text-color": k.waterLine },
    },
    {
      id: "label-road",
      type: "symbol",
      source: "omt",
      "source-layer": "transportation_name",
      minzoom: 13,
      filter: ["match", ["get", "class"], ["motorway", "trunk", "primary", "secondary", "tertiary"], true, false],
      layout: {
        "symbol-placement": "line",
        "text-field": ["coalesce", ["get", "ref"], NAME],
        "text-font": FONT,
        "text-size": 12,
      },
      paint: halo,
    },
    {
      id: "label-place",
      type: "symbol",
      source: "omt",
      "source-layer": "place",
      filter: [
        "any",
        ["match", ["get", "class"], ["city", "town"], true, false],
        ["all", [">=", ["zoom"], PARCEL_MIN_ZOOM], ["match", ["get", "class"], ["village", "suburb", "hamlet"], true, false]],
      ],
      layout: {
        "text-field": NAME,
        "text-font": FONT,
        "text-size": ["match", ["get", "class"], "city", 16, "town", 14, 13],
        "text-max-width": 8,
      },
      paint: halo,
    },
  ];
}

function overlayLayers(k: ReturnType<typeof colours>, visible: Record<Overlay, boolean>): LayerSpecification[] {
  const vis = (o: Overlay) => ({ visibility: visible[o] ? ("visible" as const) : ("none" as const) });
  const heat = (fallback: string): ExpressionSpecification => [
    "match",
    ["get", "h"],
    1,
    k.heat1,
    2,
    k.heat2,
    3,
    k.heat3,
    fallback,
  ];
  const halo = { "text-color": k.label, "text-halo-color": k.halo, "text-halo-width": 1.5 };
  return [
    {
      id: "ll-zones-fill",
      type: "fill",
      source: "ll-zones",
      "source-layer": "zones",
      layout: vis("zones"),
      paint: {
        "fill-color": [
          "match",
          ["get", "zone_code"],
          "R",
          k.heat2,
          "M",
          k.heat3,
          "C",
          k.accent,
          "I",
          k.down,
          "A",
          k.farmland,
          "CZ",
          k.forest,
          "RO",
          k.grass,
          k.tint,
        ],
        "fill-opacity": 0.3,
      },
    },
    {
      id: "ll-zones-line",
      type: "line",
      source: "ll-zones",
      "source-layer": "zones",
      layout: vis("zones"),
      paint: { "line-color": k.primary, "line-width": 1, "line-opacity": 0.6 },
    },
    {
      id: "ll-water-fill",
      type: "fill",
      source: "ll-infra",
      "source-layer": "infra",
      filter: ["==", ["get", "feature_type"], "water_body"],
      layout: vis("water"),
      paint: { "fill-color": k.water, "fill-opacity": 0.85 },
    },
    {
      id: "ll-water-line",
      type: "line",
      source: "ll-infra",
      "source-layer": "infra",
      filter: ["==", ["get", "feature_type"], "water_body"],
      layout: vis("water"),
      paint: { "line-color": k.waterLine, "line-width": 1.5 },
    },
    {
      id: "ll-villages-fill",
      type: "fill",
      source: "ll-villages",
      "source-layer": "villages",
      maxzoom: PARCEL_MIN_ZOOM,
      layout: vis("parcels"),
      paint: { "fill-color": heat(k.border), "fill-opacity": 0.75 },
    },
    {
      id: "ll-villages-line",
      type: "line",
      source: "ll-villages",
      "source-layer": "villages",
      maxzoom: PARCEL_MIN_ZOOM,
      layout: vis("parcels"),
      paint: { "line-color": k.surface, "line-width": 1.5 },
    },
    {
      id: "ll-parcels-fill",
      type: "fill",
      source: "ll-parcels",
      "source-layer": "parcels",
      minzoom: PARCEL_MIN_ZOOM,
      layout: vis("parcels"),
      paint: { "fill-color": heat(k.border), "fill-opacity": 0.9 },
    },
    {
      // DESIGN.md asks for a 2px surface outline; at z14 parcels are 3 to 5 px wide, so the width grows with zoom
      id: "ll-parcels-line",
      type: "line",
      source: "ll-parcels",
      "source-layer": "parcels",
      minzoom: PARCEL_MIN_ZOOM,
      layout: vis("parcels"),
      paint: {
        "line-color": k.surface,
        "line-width": ["interpolate", ["linear"], ["zoom"], 14, 0.4, 15, 1, 16, 2],
      },
    },
    {
      id: "ll-roads-casing",
      type: "line",
      source: "ll-infra",
      "source-layer": "infra",
      filter: ["match", ["get", "feature_type"], ["national_highway", "state_highway", "major_road"], true, false],
      layout: { ...vis("roads"), "line-cap": "round", "line-join": "round" },
      paint: { "line-color": k.roadCasing, "line-width": zoomWidth([[10, 3], [16, 12]]) },
    },
    {
      id: "ll-roads",
      type: "line",
      source: "ll-infra",
      "source-layer": "infra",
      filter: [
        "match",
        ["get", "feature_type"],
        ["national_highway", "state_highway", "major_road", "minor_road"],
        true,
        false,
      ],
      layout: { ...vis("roads"), "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": [
          "match",
          ["get", "feature_type"],
          ["national_highway", "state_highway"],
          k.accent,
          k.road,
        ],
        "line-width": [
          "interpolate",
          ["exponential", 1.5],
          ["zoom"],
          10,
          ["match", ["get", "feature_type"], "minor_road", 0.5, 1.5],
          16,
          ["match", ["get", "feature_type"], "minor_road", 4, 8],
        ],
      },
    },
    {
      id: "ll-coverage",
      type: "line",
      source: "ll-coverage",
      "source-layer": "coverage",
      paint: { "line-color": k.muted, "line-width": 1.2, "line-dasharray": [4, 3] },
    },
    {
      id: "ll-projects-fill",
      type: "fill",
      source: "ll-projects",
      "source-layer": "projects",
      filter: ["match", ["geometry-type"], ["Polygon", "MultiPolygon"], true, false],
      layout: vis("projects"),
      paint: { "fill-color": k.accent, "fill-opacity": 0.08 },
    },
    {
      id: "ll-projects-line",
      type: "line",
      source: "ll-projects",
      "source-layer": "projects",
      layout: { ...vis("projects"), "line-join": "round" },
      paint: { "line-color": k.accent, "line-width": 2, "line-dasharray": [3, 2.5] },
    },
    ...selectionLayers(k),
    {
      id: "ll-villages-label",
      type: "symbol",
      source: "ll-villages",
      "source-layer": "villages",
      minzoom: 11,
      maxzoom: PARCEL_MIN_ZOOM,
      layout: { ...vis("parcels"), "text-field": CLEAN_NAME, "text-font": FONT, "text-size": 12 },
      paint: halo,
    },
    {
      id: "ll-zones-label",
      type: "symbol",
      source: "ll-zones",
      "source-layer": "zones",
      minzoom: 13,
      layout: { ...vis("zones"), "text-field": ["get", "zone_code"], "text-font": FONT, "text-size": 11 },
      paint: halo,
    },
    {
      id: "ll-projects-label",
      type: "symbol",
      source: "ll-projects",
      "source-layer": "projects",
      layout: {
        ...vis("projects"),
        "text-field": ["concat", CLEAN_NAME, " (", ["coalesce", ["get", "status"], "status unknown"], ")"],
        "text-font": FONT,
        "text-size": 13,
        "symbol-placement": "point",
        "text-max-width": 10,
      },
      paint: { ...halo, "text-color": k.accent },
    },
  ];
}

function selectionLayers(k: ReturnType<typeof colours>): LayerSpecification[] {
  return [
    {
      // screener results: dots at the parcel centroids, visible at every zoom
      id: "ll-results",
      type: "circle",
      source: "results",
      paint: {
        "circle-color": k.primary,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 3, 14, 4.5, 17, 6],
        "circle-stroke-color": k.surface,
        "circle-stroke-width": 1.5,
        "circle-opacity": ["case", ["boolean", ["get", "selected"], false], 0, 0.9],
        "circle-stroke-opacity": ["case", ["boolean", ["get", "selected"], false], 0, 1],
      },
    },
    {
      id: "ll-selected-line",
      type: "line",
      source: "selected",
      paint: { "line-color": k.accent, "line-width": 3 },
    },
    {
      // the selected parcel as a dot too, so it stays findable below z14 where its outline is sub-pixel
      id: "ll-selected-point",
      type: "circle",
      source: "selected-point",
      paint: {
        "circle-color": k.accent,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 5, 14, 3, 15, 0],
        "circle-stroke-color": k.surface,
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 14, 2, 15, 0],
      },
    },
  ];
}

export type StyleData = {
  overlays: Record<Overlay, boolean>;
  results: Geo;
  selected: Geo;
  selectedPoint: Geo;
};

export function buildStyle(origin: string, data: StyleData): StyleSpecification {
  const k = colours();
  const tiles = (fn: string, minzoom = 0, maxzoom = 16): SourceSpecification => ({
    type: "vector",
    tiles: [`${origin}/tiles/${fn}/{z}/{x}/{y}`],
    minzoom,
    maxzoom,
    attribution: "LandLens (synthetic parcels)",
  });
  return {
    version: 8,
    glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
    "font-faces": {
      "Schibsted Grotesk Regular": `${origin}/fonts/SchibstedGrotesk-latin.woff2`,
      "Schibsted Grotesk Italic": `${origin}/fonts/SchibstedGrotesk-Italic-latin.woff2`,
    },
    sources: {
      omt: {
        type: "vector",
        url: OPENFREEMAP,
        attribution:
          '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>',
      },
      "ll-parcels": tiles("tiles_parcels", PARCEL_MIN_ZOOM, 16),
      "ll-villages": tiles("tiles_villages", 0, 13),
      "ll-zones": tiles("tiles_zones"),
      "ll-projects": tiles("tiles_projects"),
      "ll-infra": tiles("tiles_infra"),
      "ll-coverage": tiles("tiles_coverage", 0, 14),
      results: { type: "geojson", data: data.results },
      selected: { type: "geojson", data: data.selected },
      "selected-point": { type: "geojson", data: data.selectedPoint },
    },
    layers: [...baseLayers(k), ...overlayLayers(k, data.overlays), ...labelLayers(k)],
  };
}

/** Legend swatches, in order: below, near, above the village median. */
export const HEAT_LEGEND = ["var(--heat-1)", "var(--heat-2)", "var(--heat-3)"];
