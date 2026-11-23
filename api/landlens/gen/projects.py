"""Development projects (spec 2.12 step 6): hand-digitized GeoJSON, or a clearly marked synthetic fallback.

Input (T-M1-11): seed_inputs/projects/projects.geojson, a FeatureCollection in lon/lat, one feature per project:
  properties: name, project_type (ring_road|highway|airport|industrial_park|rail|urban_scheme),
              expected_completion (YYYY-MM-DD or null), sources (free text citations),
              statuses: [{effective_from: YYYY-MM-DD, status: proposed|sanctioned|under_construction|completed|shelved,
                          source: real|synthetic}]
Hand-digitized geometry is source='real' (spec 2.4); sourced status dates are 'real', others 'synthetic'.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import numpy as np
import shapely
from shapely.geometry import LineString, Point, shape

from .geo import seed_inputs, to_utm
from .osm import FALLBACK


@dataclass
class Project:
    name: str
    project_type: str
    geom: object            # UTM
    expected_completion: date | None
    source: str
    statuses: list          # (effective_from: date, status: str, source: str)

    def s(self, year: int, announced: float, sanctioned: float) -> float:
        """Price-model signal s_j(t) at mid-year (spec 2.12 step 8)."""
        t = date(year, 7, 1)
        past = [st for d, st, _ in self.statuses if d <= t]
        if not past or past[-1] == "shelved":
            return 0.0
        if any(st in ("sanctioned", "under_construction", "completed") for st in past):
            return sanctioned
        return announced


def _d(s):
    return date.fromisoformat(s) if s else None


def load(conn, centres: dict) -> tuple[list[Project], str]:
    f = seed_inputs() / "projects" / "projects.geojson"
    if f.exists():
        feats = json.loads(f.read_text())["features"]
        geoms = to_utm(conn, [shape(x["geometry"]) for x in feats])
        out = []
        for x, g in zip(feats, geoms, strict=True):
            p = x["properties"]
            sts = sorted((_d(s["effective_from"]), s["status"], s.get("source", "synthetic")) for s in p.get("statuses", []))
            out.append(Project(p["name"], p["project_type"], g, _d(p.get("expected_completion")), p.get("source", "real"), sts))
        return out, str(f)
    return fallback(conn, centres), "SYNTHETIC FALLBACK (no seed_inputs/projects/projects.geojson) - replace via T-M1-11"


def fallback(conn, centres: dict) -> list[Project]:
    """Status mix [assumption, owner request 2026-11-23]: the corridor roads that shape the demo window are not all
    "active". ORR and NH-163 are completed, the Inner Ring Road is only proposed; active (sanctioned or under
    construction, spec 2.4 mv_parcel_metrics) are the airport and the textile park."""
    core = shapely.centroid(shapely.MultiPoint(list(centres.values())))
    airport = to_utm(conn, [Point(79.6022, 17.9136)])[0]          # approximate Mamnoor site [assumption]
    a = np.radians(245)                                            # towards Hyderabad [assumption]
    nh_end = Point(core.x + 45000 * np.sin(a), core.y + 45000 * np.cos(a))
    textile = Point(core.x - 14000, core.y - 9000)                 # placeholder location [assumption]
    syn = "synthetic"
    return [
        Project(f"{FALLBACK} Mamnoor airport", "airport",
                shapely.union_all([airport.buffer(1200, quad_segs=8), LineString([core, airport]).buffer(30)]),
                date(2028, 12, 31), syn,
                [(date(2015, 6, 1), "proposed", syn), (date(2024, 12, 1), "sanctioned", syn)]),
        Project(f"{FALLBACK} Inner Ring Road", "ring_road", core.buffer(5000, quad_segs=32).exterior, date(2026, 12, 31), syn,
                [(date(2014, 1, 1), "proposed", syn)]),                     # still only proposed
        Project(f"{FALLBACK} Outer Ring Road", "ring_road", core.buffer(12000, quad_segs=48).exterior, date(2030, 12, 31), syn,
                [(date(2016, 1, 1), "proposed", syn), (date(2018, 3, 1), "sanctioned", syn),
                 (date(2019, 6, 1), "under_construction", syn), (date(2024, 3, 1), "completed", syn)]),
        Project(f"{FALLBACK} Kakatiya Mega Textile Park", "industrial_park", textile.buffer(1500, quad_segs=8),
                date(2027, 12, 31), syn,
                [(date(2016, 10, 1), "proposed", syn), (date(2017, 10, 1), "sanctioned", syn),
                 (date(2018, 6, 1), "under_construction", syn)]),
        Project(f"{FALLBACK} NH-163 corridor", "highway", LineString([core, nh_end]), date(2026, 6, 30), syn,
                [(date(2012, 1, 1), "proposed", syn), (date(2016, 3, 1), "sanctioned", syn),
                 (date(2018, 1, 1), "under_construction", syn), (date(2023, 6, 1), "completed", syn)]),
    ]


def base_name(p: Project) -> str:
    return p.name.replace(f"{FALLBACK} ", "")
