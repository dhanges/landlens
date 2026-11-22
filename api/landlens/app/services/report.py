"""Full parcel report (spec 2.9 report sections, FR-6; DEC-003 OQ-22).

Sections: location, zoning, environment, price_history, locality_trend, comparables, valuation, provenance.
Conditional on land type (OQ-22): agricultural -> environment comes first; urban_plot -> no soil subsection
(groundwater stays); otherwise identical. `section_order` lists the order the UI should render.
Zoning: primary zone = largest overlap; every zone with its share (spec 2.14). Source clause from
zone_type.source_document_id/source_page; NULL there -> "summarised from the KUDA land-use map legend" (DEC-005).
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from ..db import fetchall, fetchone
from . import trends, valuation

LEGEND_NOTE = "summarised from the KUDA land-use map legend"

LOCATION = """
SELECT p.parcel_id, p.survey_no, p.sub_div, p.land_type::text AS land_type, p.area_sqm, p.road_frontage_m,
       p.source::text AS parcel_source, v.village_id, v.name AS village, v.boundary_source::text AS village_source,
       m.mandal_id, m.name AS mandal, d.name AS district,
       round(ST_Y(ST_Transform(p.centroid, 4326))::numeric, 6) AS lat,
       round(ST_X(ST_Transform(p.centroid, 4326))::numeric, 6) AS lon,
       pm.nearest_highway_m, pm.nearest_water_m, pm.nearest_active_project_m, pm.nearest_active_project_id,
       j.name AS nearest_active_project, pm.price_sqm, pm.village_median_sqm, pm.price_vs_median_pct, pm.cagr_5y,
       pm.guideline_rate_sqm, pm.soil_score, pm.gw_category::text AS gw_category
FROM parcel p
JOIN village v USING (village_id) JOIN mandal m USING (mandal_id) JOIN district d USING (district_id)
LEFT JOIN mv_parcel_metrics pm USING (parcel_id)
LEFT JOIN dev_project j ON j.project_id = pm.nearest_active_project_id
WHERE p.parcel_id = %s"""

PROJECTS = """
SELECT j.project_id, j.name, j.project_type::text AS project_type, i.distance_m, j.expected_completion,
       j.source::text AS source,
       (SELECT h.status::text FROM project_status_history h
        WHERE h.project_id = j.project_id AND h.effective_from <= landlens_as_of()
        ORDER BY h.effective_from DESC LIMIT 1) AS status
FROM parcel_project_impact i JOIN dev_project j USING (project_id)
WHERE i.parcel_id = %s ORDER BY i.distance_m, j.project_id LIMIT 10"""

ZONES = """
SELECT pl.zone_id, pl.zone_code, zt.name, pz.overlap_pct, zt.permitted_uses, zt.source_document_id, zt.source_page,
       doc.title AS source_title, pl.source::text AS source
FROM parcel_zone pz JOIN plan_zone pl USING (zone_id) JOIN zone_type zt USING (zone_code)
LEFT JOIN document doc ON doc.document_id = zt.source_document_id
WHERE pz.parcel_id = %s ORDER BY pz.overlap_pct DESC, pl.zone_id"""

SOIL = """
SELECT s.sample_id, s.sampled_on, s.ph, s.organic_carbon_pct, s.n_kg_ha, s.p_kg_ha, s.k_kg_ha, s.texture,
       round(ST_Distance(s.geom, p.centroid)::numeric, 1) AS distance_m, s.source::text AS source
FROM parcel p CROSS JOIN LATERAL (SELECT * FROM soil_sample s ORDER BY s.geom <-> p.centroid LIMIT 3) s
WHERE p.parcel_id = %s ORDER BY distance_m"""

GROUNDWATER = """
SELECT assessment_year, extraction_pct, category::text AS category, source::text AS source
FROM gw_assessment WHERE mandal_id = %s ORDER BY assessment_year"""

SALES = """
SELECT txn_id, registered_on, consideration_inr, area_sqm, round(consideration_inr / area_sqm, 2) AS price_sqm,
       doc_no, source::text AS source
FROM sale_transaction WHERE parcel_id = %s ORDER BY registered_on, txn_id"""

GUIDELINE_SOURCE = """
SELECT DISTINCT source::text AS source FROM guideline_rate WHERE village_id = %s AND land_class = %s::land_type"""


def _sources(rows: list[dict]) -> list[str]:
    return sorted({r["source"] for r in rows if r.get("source")})


async def build(pool: AsyncConnectionPool, parcel_id: int) -> dict | None:
    loc = await fetchone(pool, LOCATION, (parcel_id,))
    if loc is None:
        return None
    lt = loc["land_type"]
    projects = await fetchall(pool, PROJECTS, (parcel_id,))
    zones = await fetchall(pool, ZONES, (parcel_id,))
    soil = await fetchall(pool, SOIL, (parcel_id,)) if lt != "urban_plot" else []
    gw = await fetchall(pool, GROUNDWATER, (loc["mandal_id"],))
    sales = await fetchall(pool, SALES, (parcel_id,))
    series = await trends.series(pool, "village", loc["village_id"], lt)
    val, comps = await valuation.value(pool, parcel_id)
    guideline_src = await fetchall(pool, GUIDELINE_SOURCE, (loc["village_id"], lt))

    location = {k: loc[k] for k in ("parcel_id", "survey_no", "sub_div", "land_type", "area_sqm", "road_frontage_m",
                                    "village_id", "village", "mandal_id", "mandal", "district", "lat", "lon")}
    location["distances_m"] = {"highway": loc["nearest_highway_m"], "water": loc["nearest_water_m"],
                               "active_project": loc["nearest_active_project_m"]}
    location["nearest_active_project"] = ({"project_id": loc["nearest_active_project_id"],
                                           "name": loc["nearest_active_project"]}
                                          if loc["nearest_active_project_id"] else None)
    location["projects_within_10km"] = projects

    primary = zones[0] if zones else None
    zoning = {
        "primary_zone": primary["zone_code"] if primary else None,
        "primary_zone_name": primary["name"] if primary else None,
        "overlap_pct": primary["overlap_pct"] if primary else None,
        "permitted_uses": primary["permitted_uses"] if primary else None,
        "source_clause": (None if not primary else
                          {"document_id": primary["source_document_id"], "title": primary["source_title"],
                           "page": primary["source_page"]} if primary["source_document_id"] else
                          {"document_id": None, "note": LEGEND_NOTE}),
        "zones": [{k: z[k] for k in ("zone_code", "name", "overlap_pct", "source")} for z in zones],
    }
    environment = {"groundwater": {"mandal_id": loc["mandal_id"], "latest_category": loc["gw_category"],
                                   "trend": gw}}
    if lt != "urban_plot":
        environment["soil"] = {"soil_score": loc["soil_score"], "nearest_samples": soil}
    comparables = [{"parcel_id": c.parcel_id, "village_id": c.village_id, "registered_on": c.registered_on,
                    "price_sqm": round(c.price_sqm, 2), "adjusted_price_sqm": round(c.adjusted_price_sqm, 2),
                    "distance_m": round(c.distance_m, 1), "area_sqm": c.area_sqm,
                    "factors": {k: round(v, 4) for k, v in c.factors.items()}} for c in comps]
    provenance = {
        "parcel": loc["parcel_source"], "village_boundary": loc["village_source"],
        "sales": _sources(sales), "zones": _sources(zones), "projects": _sources(projects),
        "soil": _sources(soil), "groundwater": _sources(gw), "guideline_rate": _sources(guideline_src),
        "valuation": "derived from the comparable sales listed in comparables",
    }
    provenance["synthetic_fields"] = sorted(k for k, v in provenance.items()
                                            if v == "synthetic" or (isinstance(v, list) and "synthetic" in v))
    order = (["environment", "location", "zoning", "price_history", "locality_trend", "comparables", "valuation"]
             if lt == "agricultural" else
             ["location", "zoning", "environment", "price_history", "locality_trend", "comparables", "valuation"])
    order.append("provenance")
    sections = {"location": location, "zoning": zoning, "environment": environment, "price_history": sales,
                "locality_trend": {"village_id": loc["village_id"], "land_type": lt, "series": series},
                "comparables": comparables, "valuation": val, "provenance": provenance}
    return {"parcel_id": parcel_id, "land_type": lt, "section_order": order, **{k: sections[k] for k in order}}
