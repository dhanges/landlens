"""Rule-based valuation (FR-7, ADR-009, spec 2.8 Q3 and 2.14; DEC-003 OQ-18).

Comparables: the 10 nearest parcels of the same land type whose latest sale is within 36 months of the as-of
date and whose centroid is within 5 km (spec 2.8 Q3, KNN on parcel_centroid_gix). Fewer than 10: widen to 10 km
and 60 months, confidence "low". Fewer than 3 even then: no range, only the locality median (spec 2.14).

Each comparable's price per sq m is adjusted to the subject with four multiplicative factors. The coefficients
are HAND-SET (OQ-18 trade-off): documented here, not fitted to the generator.
- area:      (A_subject / A_comp) ** AREA_ELASTICITY. Larger plots sell for less per sq m.
- frontage:  (1 + FRONTAGE_PREMIUM) ** (has_frontage_subject - has_frontage_comp). Road frontage > 0 counts.
- project:   exp(-PROJECT_DECAY_PER_KM * (d_subject - d_comp) / 1000), distances to the nearest active project
             capped at PROJECT_CAP_M. Closer to an active project is worth more.
- time:      village index from the comparable's sale year to the valuation year: median(Y_val) / median(Y_sale)
             in the comparable's village and land type (mv_village_price_index), where Y_val is the latest year
             with sales up to the as-of year. 1 when either year has no median.
p25/p50/p75 are percentile_cont-style quantiles of the adjusted prices. Drivers: per factor, the signed median %
effect over the comparables. Confidence: high = 10 comparables within 5 km / 36 months and median distance
<= 2 km; medium = 10 within 5 km / 36 months otherwise; low = widened search with >= 3; none = under 3.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date

from psycopg_pool import AsyncConnectionPool

from ..db import fetchall, fetchone

AREA_ELASTICITY = -0.10
FRONTAGE_PREMIUM = 0.05
PROJECT_DECAY_PER_KM = 0.02
PROJECT_CAP_M = 10_000.0
N_COMPS = 10
BASE = {"radius_m": 5000, "months": 36}
WIDE = {"radius_m": 10000, "months": 60}
HIGH_MEDIAN_DIST_M = 2000
MIN_FOR_RANGE = 3
FACTORS = ("area", "frontage", "project", "time")


@dataclass
class Subject:
    parcel_id: int
    land_type: str
    area_sqm: float
    road_frontage_m: float
    nearest_active_project_m: float | None
    village_median_sqm: float | None
    centroid_hex: str = ""


@dataclass
class Comp:
    parcel_id: int
    village_id: int
    area_sqm: float
    road_frontage_m: float
    nearest_active_project_m: float | None
    registered_on: date
    price_sqm: float
    distance_m: float
    factors: dict = field(default_factory=dict)
    adjusted_price_sqm: float | None = None


def _quantiles(xs: list[float]) -> tuple[float, float, float]:
    q = statistics.quantiles(xs, n=4, method="inclusive")     # matches percentile_cont
    return q[0], q[1], q[2]


def adjust(subject: Subject, comps: list[Comp], index: dict[tuple[int, int], float], val_year: dict[int, int]) -> None:
    """Fill comp.factors and comp.adjusted_price_sqm. index[(village_id, yr)] = median; val_year[village_id] = Y_val."""
    s_front = 1 if subject.road_frontage_m > 0 else 0
    for c in comps:
        f = {"area": (subject.area_sqm / c.area_sqm) ** AREA_ELASTICITY if c.area_sqm > 0 else 1.0,
             "frontage": (1 + FRONTAGE_PREMIUM) ** (s_front - (1 if c.road_frontage_m > 0 else 0))}
        if subject.nearest_active_project_m is not None and c.nearest_active_project_m is not None:
            ds = min(subject.nearest_active_project_m, PROJECT_CAP_M)
            dc = min(c.nearest_active_project_m, PROJECT_CAP_M)
            f["project"] = math.exp(-PROJECT_DECAY_PER_KM * (ds - dc) / 1000)
        else:
            f["project"] = 1.0
        y_val = val_year.get(c.village_id)
        m_val = index.get((c.village_id, y_val)) if y_val is not None else None
        m_sale = index.get((c.village_id, c.registered_on.year))
        f["time"] = m_val / m_sale if m_val and m_sale else 1.0
        c.factors = f
        c.adjusted_price_sqm = c.price_sqm * math.prod(f.values())


def confidence(n: int, widened: bool, median_dist_m: float | None) -> str:
    if n < MIN_FOR_RANGE:
        return "none"
    if widened:
        return "low"
    return "high" if median_dist_m is not None and median_dist_m <= HIGH_MEDIAN_DIST_M else "medium"


def summarise(subject: Subject, comps: list[Comp], widened: bool, as_of: date) -> dict:
    n = len(comps)
    med_dist = statistics.median(c.distance_m for c in comps) if comps else None
    conf = confidence(n, widened, med_dist)
    search = WIDE if widened else BASE
    out = {"method": "rule_based_comparables", "as_of": as_of.isoformat(), "confidence": conf,
           "n_comparables": n, "search_radius_m": search["radius_m"], "search_months": search["months"],
           "median_distance_m": round(med_dist, 1) if med_dist is not None else None,
           "locality_median_sqm": subject.village_median_sqm,
           "p25_sqm": None, "p50_sqm": None, "p75_sqm": None, "p25_inr": None, "p50_inr": None, "p75_inr": None,
           "drivers": [], "coefficients": {"area_elasticity": AREA_ELASTICITY, "frontage_premium": FRONTAGE_PREMIUM,
                                           "project_decay_per_km": PROJECT_DECAY_PER_KM}}
    if conf == "none":
        out["note"] = "Fewer than 3 comparable sales: no range, locality median only."
        return out
    p25, p50, p75 = _quantiles([c.adjusted_price_sqm for c in comps])
    out.update(p25_sqm=round(p25, 2), p50_sqm=round(p50, 2), p75_sqm=round(p75, 2),
               p25_inr=round(p25 * subject.area_sqm), p50_inr=round(p50 * subject.area_sqm),
               p75_inr=round(p75 * subject.area_sqm))
    out["drivers"] = [{"factor": k, "median_effect_pct": round(100 * (statistics.median(c.factors[k] for c in comps) - 1), 2)}
                      for k in FACTORS]
    if widened:
        out["note"] = "Fewer than 10 comparables within 5 km and 36 months: search widened to 10 km and 60 months."
    return out


SUBJECT = """
SELECT p.parcel_id, p.land_type::text AS land_type, p.area_sqm, p.road_frontage_m, ST_AsHexEWKB(p.centroid) AS hex,
       pm.nearest_active_project_m, pm.village_median_sqm, landlens_as_of() AS as_of
FROM parcel p LEFT JOIN mv_parcel_metrics pm USING (parcel_id) WHERE p.parcel_id = %s"""

COMPARABLES = """
SELECT p.parcel_id, p.village_id, p.area_sqm, p.road_frontage_m, pm.nearest_active_project_m,
       t.registered_on, t.price_sqm, ST_Distance(p.centroid, %(pt)s::geometry) AS distance_m
FROM parcel p
JOIN LATERAL (
  SELECT s.registered_on, s.consideration_inr / s.area_sqm AS price_sqm FROM sale_transaction s
  WHERE s.parcel_id = p.parcel_id
    AND s.registered_on > landlens_as_of() - make_interval(months => %(months)s)
    AND s.registered_on <= landlens_as_of()
  ORDER BY s.registered_on DESC, s.txn_id DESC LIMIT 1) t ON true
LEFT JOIN mv_parcel_metrics pm ON pm.parcel_id = p.parcel_id
WHERE p.land_type = %(lt)s::land_type AND p.parcel_id <> %(pid)s
  AND ST_DWithin(p.centroid, %(pt)s::geometry, %(radius)s)
ORDER BY p.centroid <-> %(pt)s::geometry, p.parcel_id
LIMIT %(n)s"""

INDEX = """
SELECT village_id, yr, median_price_sqm FROM mv_village_price_index
WHERE land_type = %(lt)s::land_type AND village_id = ANY(%(vids)s) AND yr <= extract(year FROM landlens_as_of())"""


async def _comps(pool: AsyncConnectionPool, s: Subject, search: dict) -> list[Comp]:
    rows = await fetchall(pool, COMPARABLES, {"pt": s.centroid_hex, "lt": s.land_type, "pid": s.parcel_id,
                                              "radius": search["radius_m"], "months": search["months"], "n": N_COMPS})
    return [Comp(**r) for r in rows]


async def value(pool: AsyncConnectionPool, parcel_id: int) -> tuple[dict, list[Comp]] | None:
    r = await fetchone(pool, SUBJECT, (parcel_id,))
    if r is None:
        return None
    s = Subject(parcel_id=r["parcel_id"], land_type=r["land_type"], area_sqm=r["area_sqm"],
                road_frontage_m=r["road_frontage_m"], nearest_active_project_m=r["nearest_active_project_m"],
                village_median_sqm=r["village_median_sqm"], centroid_hex=r["hex"])
    comps = await _comps(pool, s, BASE)
    widened = len(comps) < N_COMPS
    if widened:
        comps = await _comps(pool, s, WIDE)
    index: dict[tuple[int, int], float] = {}
    val_year: dict[int, int] = {}
    if comps:
        for row in await fetchall(pool, INDEX, {"lt": s.land_type, "vids": sorted({c.village_id for c in comps})}):
            index[(row["village_id"], row["yr"])] = row["median_price_sqm"]
            val_year[row["village_id"]] = max(val_year.get(row["village_id"], 0), row["yr"])
    adjust(s, comps, index, val_year)
    return summarise(s, comps, widened, r["as_of"]), comps
