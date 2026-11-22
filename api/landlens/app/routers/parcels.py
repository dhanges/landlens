"""GET /parcels/at and /parcels/{id}/summary (spec 2.9, FR-3; DEC-004 OQ-37; DEC-003 OQ-29).

/parcels/at distinguishes three 404s (spec 2.14, DEC-004):
- outside_coverage: the point is in no village cell (the study area is the union of the village cells);
- outside_parcel_window: inside the study area but outside the parcel window (parcel_coverage);
- no_parcel_at_point: inside the window but on no parcel (a gap between parcels).
The summary is free; `unlocked` reflects report_unlock when a session cookie is present, else false.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request

from ..db import fetchone
from ..errors import ApiError
from ..security import optional_user

router = APIRouter(tags=["parcels"])
PARCEL_ID = Path(ge=1, le=2**63 - 1)

SUMMARY = """
SELECT p.parcel_id, p.village_id, v.name AS village, v.mandal_id, m.name AS mandal, p.survey_no, p.sub_div,
       p.land_type, p.area_sqm, pm.zone_code, zt.name AS zone_name, pm.village_median_sqm, pm.price_sqm,
       pm.price_vs_median_pct, pm.cagr_5y, pm.nearest_active_project_m, j.name AS nearest_active_project, p.source,
       ST_AsGeoJSON(ST_Transform(p.geom, 4326), 6)::json AS geometry,
       round(ST_Y(ST_Transform(p.centroid, 4326))::numeric, 6) AS lat,
       round(ST_X(ST_Transform(p.centroid, 4326))::numeric, 6) AS lon,
       (%(uid)s::bigint IS NOT NULL AND EXISTS (SELECT 1 FROM report_unlock r
                                                WHERE r.user_id = %(uid)s AND r.parcel_id = p.parcel_id)) AS unlocked
FROM parcel p
JOIN village v USING (village_id)
JOIN mandal m USING (mandal_id)
LEFT JOIN mv_parcel_metrics pm USING (parcel_id)
LEFT JOIN zone_type zt ON zt.zone_code = pm.zone_code
LEFT JOIN dev_project j ON j.project_id = pm.nearest_active_project_id
WHERE p.parcel_id = %(pid)s"""

AT = """
WITH pt AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 32644) AS g)
SELECT (SELECT p.parcel_id FROM parcel p, pt WHERE ST_Intersects(p.geom, pt.g) ORDER BY p.parcel_id LIMIT 1)
         AS parcel_id,
       EXISTS (SELECT 1 FROM village v, pt WHERE ST_Intersects(v.geom, pt.g)) AS in_study_area,
       EXISTS (SELECT 1 FROM parcel_coverage c, pt WHERE ST_Intersects(c.geom, pt.g)) AS in_window
FROM pt"""


async def summary_row(pool, parcel_id: int, user_id: int | None) -> dict:
    row = await fetchone(pool, SUMMARY, {"pid": parcel_id, "uid": user_id})
    if row is None:
        raise ApiError(404, "parcel_not_found", f"No parcel with id {parcel_id}.")
    return row


@router.get("/parcels/at")
async def parcel_at(request: Request, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                    user_id: int | None = Depends(optional_user)) -> dict:
    """The parcel summary at a WGS84 point, or 404 outside_coverage / outside_parcel_window / no_parcel_at_point."""
    hit = await fetchone(request.app.state.pool, AT, {"lat": lat, "lon": lon})
    if hit["parcel_id"] is not None:
        return await summary_row(request.app.state.pool, hit["parcel_id"], user_id)
    if not hit["in_study_area"]:
        raise ApiError(404, "outside_coverage", "LandLens covers the KUDA area only.")
    if not hit["in_window"]:
        raise ApiError(404, "outside_parcel_window",
                       "Parcels are generated for the demo window only; village data is still available here.")
    raise ApiError(404, "no_parcel_at_point", "There is no parcel at this point.")


@router.get("/parcels/{parcel_id}/summary")
async def parcel_summary(request: Request, parcel_id: int = PARCEL_ID,
                         user_id: int | None = Depends(optional_user)) -> dict:
    """Free summary: village, land type, area, primary zone, village median price, 5-year growth, nearest active
    project, the outline (GeoJSON, WGS84) and whether you unlocked it."""
    return await summary_row(request.app.state.pool, parcel_id, user_id)
