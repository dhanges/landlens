"""Synthetic data generator, spec 2.12 steps 2-11 (steps 1, 6 live in osm.py / projects.py, step 12 in load.py).

Everything is in EPSG:32644 metres and driven by one numpy Generator, so the same seed and scale factor give the
same data. Values that stand in for missing real inputs are labelled "[fallback]".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon

from . import params
from .geo import seed_inputs
from .osm import FALLBACK, BaseLayers
from .projects import base_name

LAND_TYPES = ("urban_plot", "peri_urban", "agricultural")


def as_multi(g):
    if isinstance(g, MultiPolygon):
        return g
    if isinstance(g, Polygon):
        return MultiPolygon([g])
    polys = [p for p in getattr(g, "geoms", []) if isinstance(p, (Polygon, MultiPolygon))]
    parts = []
    for p in polys:
        parts.extend(p.geoms if isinstance(p, MultiPolygon) else [p])
    return MultiPolygon(parts)


def largest_polygon(g):
    if isinstance(g, Polygon):
        return g
    parts = [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]
    parts += [q for p in getattr(g, "geoms", []) if isinstance(p, MultiPolygon) for q in p.geoms]
    return max(parts, key=lambda p: p.area) if parts else None


@dataclass
class World:
    seed: int
    sf: float
    study_area: object
    layers: BaseLayers
    projects: list
    villages: list = field(default_factory=list)   # dict(village_id, name, geom, mandal_id, boundary_source)
    mandals: list = field(default_factory=list)    # dict(mandal_id, district_id, name, geom, boundary_source)
    districts: list = field(default_factory=list)
    window: object = None
    window_meta: dict = field(default_factory=dict)
    parcels: dict = field(default_factory=dict)    # column arrays
    zone_types: list = field(default_factory=list)
    plan_zones: list = field(default_factory=list)  # (zone_code, geom)
    sales: dict = field(default_factory=dict)
    guideline: list = field(default_factory=list)
    soil: list = field(default_factory=list)
    gw: list = field(default_factory=list)
    notes: list = field(default_factory=list)


# ---------------------------------------------------------------- step 2: boundaries
def boundaries(w: World, rng) -> None:
    pts, names, srcs, seen = [], [], [], set()
    for name, p, src in w.layers.villages:
        key = (round(p.x), round(p.y))
        if key in seen:
            continue
        seen.add(key)
        pts.append(p)
        names.append(name)
        srcs.append(src)
    order = sorted(range(len(pts)), key=lambda i: (-round(pts[i].y), round(pts[i].x)))
    pts, names, srcs = [pts[i] for i in order], [names[i] for i in order], [srcs[i] for i in order]
    cells = shapely.voronoi_polygons(shapely.MultiPoint(pts), extend_to=w.study_area, ordered=True)
    for i, (p, cell) in enumerate(zip(pts, cells.geoms, strict=True)):
        g = as_multi(shapely.make_valid(cell.intersection(w.study_area)))
        if g.is_empty:
            continue
        w.villages.append({"village_id": i + 1, "name": names[i], "point": p, "geom": g, "boundary_source": "synthetic"})
    # OSM admin boundaries are not parsed yet: every village cell is a Voronoi cell (boundary_source synthetic).

    # mandals: no mandal boundaries or names available -> seeded k-means grouping of villages (OQ-17 fallback)
    k = min(8, len(w.villages))
    xy = np.array([[v["point"].x, v["point"].y] for v in w.villages])
    cent = xy[rng.choice(len(xy), size=k, replace=False)]
    for _ in range(25):
        lab = np.argmin(((xy[:, None, :] - cent[None, :, :]) ** 2).sum(-1), axis=1)
        cent = np.array([xy[lab == j].mean(0) if (lab == j).any() else cent[j] for j in range(k)])
    # number mandals north to south for stable ids
    rank = {j: r + 1 for r, j in enumerate(sorted(range(k), key=lambda j: (-cent[j][1], cent[j][0])))}
    for v, j in zip(w.villages, lab, strict=True):
        v["mandal_id"] = rank[int(j)]
    for j in sorted(rank.values()):
        geom = as_multi(shapely.union_all([v["geom"] for v in w.villages if v["mandal_id"] == j]))
        w.mandals.append({"mandal_id": j, "district_id": 1, "name": f"{FALLBACK} Mandal {j:02d}", "geom": geom,
                          "boundary_source": "synthetic"})
    w.districts.append({"district_id": 1, "name": f"{FALLBACK} KUDA district", "boundary_source": "synthetic",
                        "geom": as_multi(shapely.union_all([m["geom"] for m in w.mandals]))})
    w.notes.append(f"villages: {len(w.villages)} Voronoi cells; mandals: {k} k-means groups [fallback]; 1 district [fallback]")


# ---------------------------------------------------------------- step 3: land type
def land_type_at(w: World, x, y, rng) -> np.ndarray:
    cxy = np.array([[c.x, c.y] for c in w.layers.centres.values()])
    d = np.sqrt(((np.stack([x, y], 1)[:, None, :] - cxy[None]) ** 2).sum(-1)).min(1) / 1000.0
    d = d + rng.normal(0, params.LAND_TYPE_NOISE_KM, size=d.shape)
    return np.where(d < params.URBAN_KM, 0, np.where(d < params.PERI_KM, 1, 2))


# ---------------------------------------------------------------- step 4: parcels in the demo window (DEC-004)
def _land_type_zones(w: World) -> list:
    """Study area split into the noise-free land-type bands of step 3 (urban < 4 km, peri < 15 km, agri beyond)."""
    cs = list(w.layers.centres.values())
    urban = shapely.union_all([c.buffer(params.URBAN_KM * 1000, quad_segs=32) for c in cs])
    peri = shapely.union_all([c.buffer(params.PERI_KM * 1000, quad_segs=32) for c in cs])
    return [urban.intersection(w.study_area), peri.difference(urban).intersection(w.study_area),
            w.study_area.difference(peri)]


def demo_window(w: World) -> None:
    """Size the window so the expected parcel count at the spec 2.12 mean target sizes equals the SF target."""
    target = params.PARCELS_PER_SF * w.sf
    mean_area = [float(np.mean(params.TARGET_SQM[t])) for t in LAND_TYPES]
    zones = _land_type_zones(w)
    centres = list(w.layers.centres.values())
    corridors = [p for p in w.projects if base_name(p) in params.CORRIDOR_PROJECTS]

    def window(r):
        parts = [c.buffer(r, quad_segs=32) for c in centres] + \
                [p.geom.buffer(r * params.CORRIDOR_RATIO, quad_segs=16) for p in corridors]
        return shapely.union_all(parts).intersection(w.study_area)

    def expected(win):
        return sum(win.intersection(z).area / a for z, a in zip(zones, mean_area, strict=True))

    lo, hi = 50.0, 40_000.0
    for _ in range(60):
        r = (lo + hi) / 2
        win = window(r)
        e = expected(win)
        if abs(e - target) / target < params.WINDOW_TOLERANCE:
            break
        lo, hi = (r, hi) if e < target else (lo, r)
    w.window = as_multi(win)
    w.window_meta = {"core_radius_m": round(r, 1), "corridor_halfwidth_m": round(r * params.CORRIDOR_RATIO, 1),
                     "expected_parcels": int(round(e)), "area_sqkm": round(win.area / 1e6, 2)}
    w.notes.append(f"demo window (computed): core radius {r / 1000:.2f} km, corridor half-width "
                   f"{r * params.CORRIDOR_RATIO / 1000:.2f} km around {len(corridors)} corridors, "
                   f"{win.area / 1e6:.1f} sq km, expected {e:,.0f} parcels at target sizes")


def parcels(w: World, rng) -> None:
    n_target = int(round(params.PARCELS_PER_SF * w.sf))
    mean_area = np.array([np.mean(params.TARGET_SQM[t]) for t in LAND_TYPES])
    accept = (1 / mean_area) / (1 / mean_area).max()
    minx, miny, maxx, maxy = w.window.bounds
    shapely.prepare(w.window)
    xs, ys, lts = [], [], []
    have = 0
    while have < n_target:
        m = 400_000
        x, y = rng.uniform(minx, maxx, m), rng.uniform(miny, maxy, m)
        inside = shapely.contains_xy(w.window, x, y)
        x, y = x[inside], y[inside]
        lt = land_type_at(w, x, y, rng)
        keep = rng.uniform(0, 1, len(x)) < accept[lt]
        xs.append(x[keep]), ys.append(y[keep]), lts.append(lt[keep])
        have += int(keep.sum())
    x, y, lt = np.concatenate(xs)[:n_target], np.concatenate(ys)[:n_target], np.concatenate(lts)[:n_target]

    cols = {k: [] for k in ("village_id", "survey_no", "land_type", "geom", "px", "py")}
    pts = shapely.points(x, y)
    vgeoms = [v["geom"] for v in w.villages]
    tree = shapely.STRtree(vgeoms)
    pi, vi = tree.query(pts, predicate="within")
    owner = np.full(len(pts), -1)
    owner[pi] = vi
    dropped = 0
    for vidx, v in enumerate(w.villages):
        idx = np.nonzero(owner == vidx)[0]
        if len(idx) == 0:
            continue
        region = v["geom"].intersection(w.window)
        if region.is_empty:
            continue
        idx = idx[np.lexsort((x[idx], -y[idx]))]          # north-west first: stable survey numbers
        if len(idx) == 1:
            cells = [region]
        else:
            cells = list(shapely.voronoi_polygons(shapely.MultiPoint(pts[idx].tolist()), extend_to=region,
                                                  ordered=True).geoms)
        n = 0
        for j, cell in zip(idx, cells, strict=True):
            g = largest_polygon(shapely.make_valid(cell.intersection(region)))
            if g is None or g.area < params.MIN_PARCEL_SQM:
                dropped += 1
                continue
            n += 1
            cols["village_id"].append(v["village_id"])
            cols["survey_no"].append(str(n))
            cols["land_type"].append(int(lt[j]))
            cols["geom"].append(g)
            cols["px"].append(x[j])
            cols["py"].append(y[j])
    w.parcels = {k: np.array(v, dtype=object if k == "geom" or k == "survey_no" else None) for k, v in cols.items()}
    w.parcels["area"] = shapely.area(w.parcels["geom"])
    w.notes.append(f"parcels: {len(w.parcels['geom'])} of target {n_target} ({dropped} slivers dropped)")


# ---------------------------------------------------------------- step 5: road frontage
def road_frontage(w: World) -> None:
    roads = [g for ft, _, _, g, _ in w.layers.features if ft in params.ROAD_TYPES]
    geoms = w.parcels["geom"]
    front = np.zeros(len(geoms))
    if roads:
        rbuf = shapely.buffer(np.array(roads, dtype=object), params.ROAD_FRONTAGE_M, quad_segs=2)
        bnd = shapely.boundary(geoms)
        tree = shapely.STRtree(rbuf)
        pi, ri = tree.query(bnd, predicate="intersects")
        lens = shapely.length(shapely.intersection(bnd[pi], rbuf[ri]))
        np.add.at(front, pi, lens)
        front = np.minimum(front, shapely.length(bnd))
    w.parcels["frontage"] = np.round(front, 2)


# ---------------------------------------------------------------- step 7: zones
FALLBACK_ZONES = [  # DEC-005: real codes/names come from the KUDA land-use map legend (seed_inputs/zones/zone_types.json)
    ("R", "Residential", "Dwellings, home occupations, neighbourhood shops"),
    ("C", "Commercial", "Shops, offices, hotels, warehouses up to a size limit"),
    ("M", "Mixed use", "Residential and commercial uses together"),
    ("I", "Industrial", "Manufacturing, warehousing, logistics"),
    ("PSP", "Public and semi-public", "Schools, hospitals, government offices"),
    ("RO", "Recreational and open space", "Parks, playgrounds, water-front open space"),
    ("A", "Agricultural", "Farming, farmhouses, agro-processing"),
    ("CZ", "Conservation", "Water bodies and their buffers, no construction"),
]
ZONE_MIX = {0: (("R", .45), ("C", .2), ("M", .2), ("PSP", .1), ("RO", .05)),
            1: (("R", .45), ("M", .1), ("I", .15), ("PSP", .05), ("RO", .05), ("A", .2)),
            2: (("A", .8), ("I", .05), ("CZ", .1), ("R", .05))}


def zones(w: World, rng) -> None:
    f = seed_inputs() / "zones" / "zone_types.json"
    if f.exists():
        w.zone_types = [(z["zone_code"], z["name"], z["permitted_uses"]) for z in json.loads(f.read_text())]
        w.notes.append(f"zone types from {f}")
    else:
        w.zone_types = [(c, f"{FALLBACK} {n}", f"{FALLBACK} summarised placeholder: {u}") for c, n, u in FALLBACK_ZONES]
        w.notes.append("zone types: [fallback] list (replace with the KUDA land-use map legend, DEC-005)")
    codes = {c for c, _, _ in w.zone_types}
    minx, miny, maxx, maxy = w.study_area.bounds
    n = params.ZONE_SEED_POINTS_PER_SF
    x, y = rng.uniform(minx, maxx, n * 3), rng.uniform(miny, maxy, n * 3)
    inside = shapely.contains_xy(w.study_area, x, y)
    x, y = x[inside][:n], y[inside][:n]
    lt = land_type_at(w, x, y, rng)
    cells = shapely.voronoi_polygons(shapely.MultiPoint(list(zip(x, y, strict=False))), extend_to=w.study_area, ordered=True)
    for cell, t in zip(cells.geoms, lt, strict=True):
        mix = [(c, p) for c, p in ZONE_MIX[int(t)] if c in codes] or [(next(iter(sorted(codes))), 1.0)]
        cs, ps = zip(*mix, strict=False)
        code = cs[rng.choice(len(cs), p=np.array(ps) / sum(ps))]
        g = as_multi(shapely.make_valid(cell.intersection(w.study_area)))
        if not g.is_empty:
            w.plan_zones.append((code, g))


# ---------------------------------------------------------------- step 8: prices
def _growth_index(rng) -> dict:
    years = list(params.SALE_YEARS)
    out = {}
    for t, g in params.GROWTH.items():
        shocks = rng.normal(0, params.GROWTH_SHOCK_SD, len(years))
        idx = np.cumprod(np.r_[1.0, 1 + g + shocks[1:]])
        idx = idx / idx[years.index(params.PRICE_BASE_YEAR)]   # B is the price level in the base year
        out[t] = dict(zip(years, idx, strict=True))
    return out


def price_model(w: World, rng):
    """Return f(x, y, land_type_idx, frontage, year) -> noise-free price per sq m (vectorised over parcels)."""
    G = _growth_index(rng)
    cxy = np.array([[c.x, c.y] for c in w.layers.centres.values()])
    eff = [(p, *params.PROJECT_EFFECT.get(base_name(p), (0.0, 1.0))) for p in w.projects]

    def f(x, y, lt, frontage, year):
        d = np.sqrt(((np.stack([x, y], 1)[:, None, :] - cxy[None]) ** 2).sum(-1)).min(1) / 1000.0
        base = np.array([params.B_INR_PER_SQM[t] for t in LAND_TYPES])[lt]
        g = np.array([G[t][year] for t in LAND_TYPES])[lt]
        proj = np.ones(len(x))
        for p, a, tau in eff:
            s = p.s(year, params.S_ANNOUNCED, params.S_SANCTIONED)
            if s and a:
                dij = shapely.distance(shapely.points(x, y), p.geom) / 1000.0
                proj *= 1 + a * s * np.exp(-dij / tau)
        return base * np.exp(-params.LAMBDA_PER_KM * d) * g * proj * (1 + params.BETA_PER_M * frontage)

    return f


# ---------------------------------------------------------------- step 9: sales
def sales(w: World, rng, price) -> None:
    P = w.parcels
    n = len(P["geom"])
    lt = P["land_type"].astype(int)
    rate = np.array([params.SALE_RATE[t] for t in LAND_TYPES])[lt]
    years = list(params.SALE_YEARS)
    counts = rng.poisson(rate[:, None], size=(n, len(years)))
    rows = {k: [] for k in ("parcel_idx", "date", "area", "consideration", "price_sqm")}
    for yi, yr in enumerate(years):
        k = counts[:, yi]
        idx = np.repeat(np.arange(n), k)
        if len(idx) == 0:
            continue
        start = date(yr, 1, 1)
        end = min(date(yr, 12, 31), params.SALE_CUTOFF)
        days = rng.integers(0, (end - start).days + 1, len(idx))
        base = price(P["px"][idx].astype(float), P["py"][idx].astype(float), lt[idx], P["frontage"][idx], yr)
        ppsqm = base * rng.lognormal(0, params.EPS_SD, len(idx))
        partial = rng.uniform(0, 1, len(idx)) < params.PARTIAL_SHARE
        frac = np.where(partial, rng.uniform(*params.PARTIAL_FRACTION, len(idx)), 1.0)
        area = np.round(P["area"][idx] * frac, 2)
        cons = np.round(ppsqm * area * rng.lognormal(0, params.CONSIDERATION_SD, len(idx)), 2)
        rows["parcel_idx"].append(idx)
        rows["date"].append(np.array([start + timedelta(days=int(d)) for d in days]))
        rows["area"].append(area)
        rows["consideration"].append(cons)
        rows["price_sqm"].append(cons / area)
    S = {k: np.concatenate(v) for k, v in rows.items()}
    order = np.lexsort((S["parcel_idx"], S["date"]))
    S = {k: v[order] for k, v in S.items()}
    keep = (S["area"] > 0) & (S["consideration"] > 0)
    S = {k: v[keep] for k, v in S.items()}
    S["txn_id"] = np.arange(1, len(S["date"]) + 1)
    w.sales = S
    w.notes.append(f"sales: {len(S['date'])} ({(S['area'] < P['area'][S['parcel_idx']] - 0.01).mean():.1%} partial)")


# ---------------------------------------------------------------- step 10: guideline rates
def guideline_rates(w: World, rng, price) -> None:
    S, P = w.sales, w.parcels
    vid = P["village_id"][S["parcel_idx"]].astype(int)
    lt = P["land_type"][S["parcel_idx"]].astype(int)
    yr = np.array([d.year for d in S["date"]])
    for v in w.villages:
        c = v["point"]
        for ti, t in enumerate(LAND_TYPES):
            m = (vid == v["village_id"]) & (lt == ti)
            for gy in params.GUIDELINE_YEARS:
                lag = m & (yr >= gy - 3) & (yr <= gy - 1)
                if lag.sum() >= 3:
                    lagged = float(np.median(S["price_sqm"][lag]))
                else:   # no local sales yet (2010, or outside the parcel window): model price at the village point
                    lagged = float(price(np.array([c.x]), np.array([c.y]), np.array([ti]), np.array([0.0]), max(gy - 1, 2010))[0])
                share = rng.uniform(*params.GUIDELINE_SHARE)
                w.guideline.append((v["village_id"], t, date(gy, 4, 1), round(lagged * share, 2)))


# ---------------------------------------------------------------- step 11: soil and groundwater
def environment(w: World, rng) -> None:
    minx, miny, maxx, maxy = w.study_area.bounds
    gx = np.arange(minx + params.SOIL_GRID_M / 2, maxx, params.SOIL_GRID_M)
    gy = np.arange(miny + params.SOIL_GRID_M / 2, maxy, params.SOIL_GRID_M)
    X, Y = np.meshgrid(gx, gy)
    X, Y = X.ravel(), Y.ravel()
    inside = shapely.contains_xy(w.study_area, X, Y)
    X, Y = X[inside], Y[inside]

    def field_():   # smooth random field in [-1, 1]: a few long-wavelength waves
        z = np.zeros(len(X))
        for _ in range(6):
            k = rng.uniform(1 / 30000, 1 / 8000)
            th = rng.uniform(0, np.pi)
            z += rng.uniform(0.5, 1) * np.sin(k * (X * np.cos(th) + Y * np.sin(th)) * 2 * np.pi + rng.uniform(0, 6.3))
        return z / np.abs(z).max()

    ph, oc, n_, p_, k_, tex = (field_() for _ in range(6))
    textures = np.array(["sandy loam", "loam", "clay loam", "black cotton clay"])
    tex_i = np.digitize(tex, np.quantile(tex, [0.25, 0.5, 0.75]))
    for i in range(len(X)):
        w.soil.append((date(2023, 1 + i % 12, 1 + i % 28), round(float(7.2 + 0.8 * ph[i]), 1),
                       round(float(0.7 + 0.35 * oc[i]), 2), round(float(250 + 80 * n_[i]), 1),
                       round(float(22 + 10 * p_[i]), 1), round(float(260 + 80 * k_[i]), 1), textures[tex_i[i]],
                       Point(X[i], Y[i])))
    for m in w.mandals:
        base, drift = rng.uniform(55, 85), rng.uniform(0.6, 1.6)
        for i, yr in enumerate(params.GW_YEARS):
            w.gw.append((m["mandal_id"], yr, round(max(0.0, base + drift * i + rng.normal(0, 2)), 1)))
