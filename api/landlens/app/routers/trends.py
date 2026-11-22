"""GET /trends/villages/{id} and /trends/mandals/{id} (spec 2.9, FR-5).

`land_type` is optional: without it, the land type with the most sales in that village or mandal is used, and
the response says which one.
"""

from __future__ import annotations

from fastapi import APIRouter, Path, Query, Request

from ..db import fetchone
from ..enums import LandType
from ..errors import ApiError
from ..services import trends

router = APIRouter(tags=["trends"])


async def _trend(request: Request, level: str, id_: int, land_type: LandType | None) -> dict:
    pool = request.app.state.pool
    if level == "village":
        row = await fetchone(pool, "SELECT v.village_id AS id, v.name, v.mandal_id FROM village v "
                                   "WHERE v.village_id = %s", (id_,))
    else:
        row = await fetchone(pool, "SELECT mandal_id AS id, name FROM mandal WHERE mandal_id = %s", (id_,))
    if row is None:
        raise ApiError(404, f"{level}_not_found", f"No {level} with id {id_}.")
    lt = land_type.value if land_type else await trends.default_land_type(pool, level, id_)
    out = {f"{level}_id": row["id"], "name": row["name"], "land_type": lt,
           "series": await trends.series(pool, level, id_, lt) if lt else []}
    if level == "village":
        out["mandal_id"] = row["mandal_id"]
    return out


@router.get("/trends/villages/{village_id}")
async def village_trend(request: Request, village_id: int = Path(ge=1, le=2**31 - 1),
                        land_type: LandType | None = Query(None)) -> dict:
    """Yearly median price per sq m, sale count, YoY (with the year it compares to) and guideline rate."""
    return await _trend(request, "village", village_id, land_type)


@router.get("/trends/mandals/{mandal_id}")
async def mandal_trend(request: Request, mandal_id: int = Path(ge=1, le=32767),
                       land_type: LandType | None = Query(None)) -> dict:
    """Same shape as the village series, computed from the mandal's sales (medians are not aggregated)."""
    return await _trend(request, "mandal", mandal_id, land_type)
