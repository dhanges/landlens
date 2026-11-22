"""Real base layers (spec 2.12 step 1): parse the Overpass export, or build a clearly marked synthetic fallback.

Export: seed_inputs/osm/*.json produced by overpass_query.ql (`out geom`). Fallback rows are source='synthetic' and
named "[fallback] ..." so they can never be mistaken for OSM data; replace them by adding the real export.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

from . import params
from .geo import seed_inputs, to_utm

FALLBACK = "[fallback]"


@dataclass
class BaseLayers:
    features: list = field(default_factory=list)   # (feature_type, name, osm_id, geom_utm, source)
    villages: list = field(default_factory=list)   # (name, point_utm, source)
    centres: dict = field(default_factory=dict)     # name -> point_utm
    origin: str = ""


def feature_type(tags: dict) -> str | None:
    hw, ref = tags.get("highway"), tags.get("ref", "")
    if hw in ("motorway", "trunk") or (hw == "primary" and ref.upper().startswith("NH")):
        return "national_highway"
    if hw == "primary" or ref.upper().startswith("SH"):
        return "state_highway"
    if hw in ("secondary", "tertiary"):
        return "major_road"
    if hw in ("unclassified", "residential"):
        return "minor_road"
    if tags.get("railway") == "rail":
        return "rail"
    if tags.get("natural") == "water" or tags.get("landuse") == "reservoir":
        return "water_body"
    if tags.get("waterway") == "river":
        return "river"
    if tags.get("amenity") in ("school", "hospital", "bus_station"):
        return tags["amenity"]
    if tags.get("landuse") == "industrial":
        return "industrial_area"
    if tags.get("aeroway") == "aerodrome":
        return "airport"
    return None


def _element_geom(el: dict):
    if el["type"] == "node":
        return Point(el["lon"], el["lat"])
    pts = [(p["lon"], p["lat"]) for p in el.get("geometry") or [] if p]
    if el["type"] == "way" and len(pts) >= 2:
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts)
        return LineString(pts)
    if el["type"] == "relation":
        outers = []
        for m in el.get("members", []):
            mp = [(p["lon"], p["lat"]) for p in m.get("geometry") or [] if p]
            if m.get("role") == "outer" and len(mp) >= 4 and mp[0] == mp[-1]:
                outers.append(Polygon(mp))
        if outers:
            return shapely.union_all(outers)
        if el.get("center"):
            return Point(el["center"]["lon"], el["center"]["lat"])
    return None


def load_export(conn, study_area) -> BaseLayers | None:
    files = sorted((seed_inputs() / "osm").glob("*.json"))
    if not files:
        return None
    feats, places = [], []
    seen = set()
    for f in files:
        for el in json.loads(f.read_text()).get("elements", []):
            key = (el["type"], el["id"])
            if key in seen:
                continue
            seen.add(key)
            tags = el.get("tags", {})
            g = _element_geom(el)
            if g is None or g.is_empty:
                continue
            if el["type"] == "node" and tags.get("place") and tags.get("name"):
                places.append((tags["name"], tags["place"], g))
                continue
            ft = feature_type(tags)
            if ft:
                osm_id = el["id"] if el["type"] == "node" else (el["id"] * 10 + (1 if el["type"] == "way" else 2))
                feats.append((ft, tags.get("name"), osm_id, g))
    utm_feats = to_utm(conn, [g for *_, g in feats])
    utm_places = to_utm(conn, [g for *_, g in places])
    out = BaseLayers(origin=f"OSM export ({', '.join(p.name for p in files)})")
    for (ft, name, osm_id, _), g in zip(feats, utm_feats, strict=True):
        g = g.intersection(study_area) if not g.within(study_area) else g
        if not g.is_empty:
            out.features.append((ft, name, osm_id, g, "osm"))
    for (name, kind, _), g in zip(places, utm_places, strict=True):
        if g.within(study_area):
            if name in params.CENTRES_LONLAT:
                out.centres[name] = g
            if kind in ("village", "hamlet", "suburb", "town"):
                out.villages.append((name, g, "osm"))
    return out


def fallback(conn, study_area, centres: dict, rng: np.random.Generator) -> BaseLayers:
    """Synthetic stand-in for the Overpass export: villages, roads, rail, water, amenities (all source='synthetic')."""
    out = BaseLayers(origin="SYNTHETIC FALLBACK (no seed_inputs/osm/*.json) - replace with the Overpass export",
                     centres=dict(centres))
    minx, miny, maxx, maxy = study_area.bounds
    core = shapely.centroid(shapely.MultiPoint(list(centres.values())))

    # ~181 revenue villages (PRD 1): jittered grid, so spacing is even and the count stable
    nx, ny = 14, 13
    xs, ys = np.linspace(minx, maxx, nx + 2)[1:-1], np.linspace(miny, maxy, ny + 2)[1:-1]
    sx, sy = (maxx - minx) / (nx + 1), (maxy - miny) / (ny + 1)
    k = 0
    for x in xs:
        for y in ys:
            p = Point(x + rng.uniform(-0.35, 0.35) * sx, y + rng.uniform(-0.35, 0.35) * sy)
            if p.within(study_area):
                k += 1
                out.villages.append((f"{FALLBACK} Village {k:03d}", p, "synthetic"))
    for name, c in centres.items():          # the three towns are villages/towns in their own right
        out.villages.append((f"{FALLBACK} {name}", c, "synthetic"))

    def add(ft, name, geom):
        g = geom.intersection(study_area)
        if not g.is_empty:
            out.features.append((ft, f"{FALLBACK} {name}", None, g, "synthetic"))

    # radial highways from the core (bearing in degrees from north) [assumption: rough directions]
    radials = {"NH-163 to Hyderabad": (245, "national_highway"), "NH-163 to Bhupalpally": (60, "national_highway"),
               "Road to Karimnagar": (325, "state_highway"), "Road to Khammam": (150, "state_highway"),
               "Road to Narsampet": (95, "major_road"), "Road to Jangaon": (215, "major_road")}
    for name, (bearing, ft) in radials.items():
        a = np.radians(bearing)
        end = Point(core.x + 60000 * np.sin(a), core.y + 60000 * np.cos(a))
        add(ft, name, LineString([core, end]))
    # minor road grid around the towns (every ~600 m within 16 km of the core), lightly jittered
    for off in np.arange(-16000, 16001, 600):
        j = rng.uniform(-80, 80)
        add("minor_road", "Local road", LineString([(core.x - 16000, core.y + off + j), (core.x + 16000, core.y + off - j)]))
        add("minor_road", "Local road", LineString([(core.x + off + j, core.y - 16000), (core.x + off - j, core.y + 16000)]))
    add("rail", "Kazipet-Warangal rail line", LineString([(core.x - 40000, core.y + 4000), (core.x + 40000, core.y - 6000)]))
    for i in range(12):
        c = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        add("water_body", f"Tank {i + 1:02d}", c.buffer(rng.uniform(150, 700), quad_segs=8))
    for ft, n in (("school", 60), ("hospital", 15), ("bus_station", 8)):
        for i in range(n):
            d = abs(rng.normal(0, 9000))
            a = rng.uniform(0, 2 * np.pi)
            add(ft, f"{ft.replace('_', ' ').title()} {i + 1:02d}", Point(core.x + d * np.sin(a), core.y + d * np.cos(a)))
    add("industrial_area", "Industrial estate", Point(core.x + 6000, core.y - 5000).buffer(900, quad_segs=4))
    return out


def load(conn, study_area, rng) -> BaseLayers:
    layers = load_export(conn, study_area)
    cfg_centres = dict(zip(params.CENTRES_LONLAT, to_utm(conn, [Point(*c) for c in params.CENTRES_LONLAT.values()]),
                           strict=True))
    if layers is None:
        return fallback(conn, study_area, cfg_centres, rng)
    for name, pt in cfg_centres.items():
        layers.centres.setdefault(name, pt)     # config coordinates when OSM lacks a place node
    if len(layers.villages) < 20:
        raise SystemExit(f"osm-load: only {len(layers.villages)} village points in the export; check the query")
    return layers
