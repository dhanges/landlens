"""GET /search (spec 2.9, FR-2; DEC-003 OQ-21).

Villages: trigram word similarity (pg_trgm `<%`, village_name_trgm), tolerant of transliteration variants such
as Hanmakonda for Hanamkonda, plus a case-insensitive substring match. Parcels: when q looks like a survey
number ("123", "123/A", "123-2"), match survey_no (and sub_div when given), within village_id when given.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query, Request

from ..db import fetchall, in_transaction

router = APIRouter(tags=["search"])
# word_similarity threshold for `<%`: 0.4 instead of the 0.6 default, so one-letter transliteration swaps
# (Hanmakonda / Hanamkonda: 0.47) still match. Set per transaction, so the trigram index stays usable.
WORD_SIMILARITY_THRESHOLD = "0.4"
SURVEY_RE = re.compile(r"^\s*(\d{1,6})\s*(?:[/-]\s*([A-Za-z0-9]{1,8}))?\s*$")

VILLAGES = """
SELECT v.village_id, v.name, m.name AS mandal, round(word_similarity(%(q)s, v.name)::numeric, 3) AS similarity,
       round(ST_Y(ST_Transform(ST_PointOnSurface(v.geom), 4326))::numeric, 6) AS lat,
       round(ST_X(ST_Transform(ST_PointOnSurface(v.geom), 4326))::numeric, 6) AS lon
FROM village v JOIN mandal m USING (mandal_id)
WHERE %(q)s <%% v.name OR v.name ILIKE %(pat)s
ORDER BY similarity DESC, v.name
LIMIT %(lim)s"""

PARCELS = """
SELECT p.parcel_id, p.village_id, v.name AS village, p.survey_no, p.sub_div, p.land_type, p.area_sqm,
       round(ST_Y(ST_Transform(p.centroid, 4326))::numeric, 6) AS lat,
       round(ST_X(ST_Transform(p.centroid, 4326))::numeric, 6) AS lon
FROM parcel p JOIN village v USING (village_id)
WHERE p.survey_no = %(sn)s
  AND (%(sd)s::text IS NULL OR p.sub_div = %(sd)s)
  AND (%(vid)s::integer IS NULL OR p.village_id = %(vid)s)
ORDER BY p.village_id, p.sub_div
LIMIT %(lim)s"""


def _like_pattern(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/search")
async def search(request: Request, q: str = Query(min_length=1, max_length=100),
                 limit: int = Query(10, ge=1, le=50),
                 village_id: int | None = Query(None, ge=1, le=2**31 - 1)) -> dict:
    """Fuzzy village search, plus survey-number matches when q looks like one. Each hit has a WGS84 point
    (village: a point on its surface; parcel: its centroid) for the map to fly to."""
    pool = request.app.state.pool
    q = q.strip()
    async def villages_tx(conn):
        await conn.execute("SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)",
                           (WORD_SIMILARITY_THRESHOLD,))
        cur = await conn.execute(VILLAGES, {"q": q, "pat": _like_pattern(q), "lim": limit})
        return await cur.fetchall()

    villages = await in_transaction(pool, villages_tx) if q else []
    parcels = []
    m = SURVEY_RE.match(q)
    if m:
        parcels = await fetchall(pool, PARCELS, {"sn": m.group(1), "sd": m.group(2), "vid": village_id, "lim": limit})
    return {"villages": villages, "parcels": parcels}
