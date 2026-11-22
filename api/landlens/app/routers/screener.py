"""POST /screener and GET /screener/options (spec 2.8 Q6, 2.9, FR-4; DEC-003 OQ-20).

- Filters are whitelisted: each key maps to one fixed SQL fragment with a bound parameter; unknown keys -> 422
  (pydantic extra="forbid"). No user string ever reaches the SQL text.
- Sorts: cagr_5y (default, DESC, served by I5), price_sqm, area_sqm, nearest_active_project_m; each keyset on
  (column, parcel_id), so page 50 costs what page 1 costs.
- NULLs in the sort column come after every non-NULL value: the cursor has a phase, "n" (non-NULL rows, keyset
  on (col, parcel_id)) then "z" (NULL rows, keyset on parcel_id), each phase index-friendly on its own.
- approx_total: exact count(*) of the filtered view on page 1 only, carried in the cursor.
- The cursor is opaque base64url JSON. It is bound to the filters and sort via a hash; a mismatch -> 422.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import time
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from ..db import fetchall, fetchone
from ..enums import GwCategory, LandType
from ..errors import ApiError

router = APIRouter(tags=["screener"])

SORTS = {"cagr_5y": "desc", "price_sqm": "asc", "area_sqm": "desc", "nearest_active_project_m": "asc"}
COLUMNS = ("parcel_id, village_id, village_name, mandal_id, land_type, zone_code, area_sqm, price_sqm, "
           "village_median_sqm, cagr_5y, nearest_active_project_m, nearest_highway_m, gw_category, soil_score, "
           "guideline_rate_sqm")
OPTIONS_TTL_S = 300


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    land_type: LandType | None = None
    zone_code: list[Annotated[str, Field(min_length=1, max_length=20)]] | None = Field(None, max_length=20, validation_alias=AliasChoices("zone_code", "zone_code[]"))
    area_sqm_min: float | None = Field(None, ge=0)
    area_sqm_max: float | None = Field(None, ge=0)
    price_sqm_min: float | None = Field(None, ge=0)
    price_sqm_max: float | None = Field(None, ge=0)
    max_active_project_m: float | None = Field(None, ge=0)
    max_highway_m: float | None = Field(None, ge=0)
    min_cagr_5y: float | None = Field(None, ge=-1, le=10)
    exclude_gw: list[GwCategory] | None = Field(None, max_length=4,
                                                validation_alias=AliasChoices("exclude_gw", "exclude_gw[]"))
    min_soil_score: float | None = Field(None, ge=0, le=100)
    mandal_id: list[Annotated[int, Field(ge=1, le=32767)]] | None = Field(None, max_length=100,
                                        validation_alias=AliasChoices("mandal_id", "mandal_id[]"))


# key -> fixed SQL fragment; the value is bound as %(key)s
FRAGMENTS = {
    "land_type": "land_type = %(land_type)s::land_type",
    "zone_code": "zone_code = ANY(%(zone_code)s::text[])",
    "area_sqm_min": "area_sqm >= %(area_sqm_min)s",
    "area_sqm_max": "area_sqm <= %(area_sqm_max)s",
    "price_sqm_min": "price_sqm >= %(price_sqm_min)s",
    "price_sqm_max": "price_sqm <= %(price_sqm_max)s",
    "max_active_project_m": "nearest_active_project_m <= %(max_active_project_m)s",
    "max_highway_m": "nearest_highway_m <= %(max_highway_m)s",
    "min_cagr_5y": "cagr_5y >= %(min_cagr_5y)s",
    "exclude_gw": "(gw_category IS NULL OR gw_category <> ALL(%(exclude_gw)s::gw_category[]))",
    "min_soil_score": "soil_score >= %(min_soil_score)s",
    "mandal_id": "mandal_id = ANY(%(mandal_id)s::smallint[])",
}


class ScreenerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: Filters = Field(default_factory=Filters)
    sort: Literal["cagr_5y", "price_sqm", "area_sqm", "nearest_active_project_m"] = "cagr_5y"
    order: Literal["asc", "desc"] | None = None
    cursor: str | None = Field(None, max_length=1000)
    limit: int = Field(50, ge=1, le=100)


def _where(f: Filters) -> tuple[list[str], dict]:
    clauses, params = [], {}
    for key, value in f.model_dump(exclude_none=True).items():
        if isinstance(value, list) and not value:
            continue
        clauses.append(FRAGMENTS[key])
        params[key] = [v.value if hasattr(v, "value") else v for v in value] if isinstance(value, list) else (
            value.value if hasattr(value, "value") else value)
    return clauses, params


def _fingerprint(body: ScreenerRequest, order: str) -> str:
    canon = json.dumps([body.filters.model_dump(mode="json", exclude_none=True), body.sort, order], sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def _encode(c: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(c, separators=(",", ":")).encode()).decode().rstrip("=")


def _decode(s: str, fp: str) -> dict:
    try:
        c = json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))
        ok = (isinstance(c, dict) and c.get("f") == fp and c.get("p") in ("n", "z") and isinstance(c.get("i"), int)
              and (c.get("k") is None or isinstance(c.get("k"), str)) and isinstance(c.get("t"), int))
        if ok and c["k"] is not None:
            Decimal(c["k"])
    except (ValueError, binascii.Error, ArithmeticError, UnicodeDecodeError):
        ok = False
    if not ok:
        raise ApiError(422, "invalid_cursor", "The cursor is malformed or belongs to other filters or sort.")
    return c


@router.post("/screener")
async def screener(body: ScreenerRequest, request: Request) -> dict:
    """Filtered, sorted, keyset-paginated parcels from mv_parcel_metrics: {items, next_cursor, approx_total}."""
    pool = request.app.state.pool
    col, order = body.sort, body.order or SORTS[body.sort]
    cmp, direction = ("<", "DESC") if order == "desc" else (">", "ASC")
    fp = _fingerprint(body, order)
    clauses, params = _where(body.filters)
    cur = _decode(body.cursor, fp) if body.cursor else None

    if cur is None:
        where = " AND ".join(clauses) or "true"
        total = (await fetchone(pool, f"SELECT count(*) AS n FROM mv_parcel_metrics WHERE {where}", params))["n"]
    else:
        total = cur["t"]

    want = body.limit + 1
    rows: list[dict] = []
    if cur is None or cur["p"] == "n":            # phase n: non-NULL sort values, keyset on (col, parcel_id)
        cl = clauses + [f"{col} IS NOT NULL"]
        p = dict(params)
        if cur is not None:
            cl.append(f"({col}, parcel_id) {cmp} (%(_k)s::numeric, %(_i)s::bigint)")
            p.update(_k=cur["k"], _i=cur["i"])
        rows = await fetchall(pool, f"SELECT {COLUMNS} FROM mv_parcel_metrics WHERE {' AND '.join(cl)} "
                                    f"ORDER BY {col} {direction}, parcel_id {direction} LIMIT {want}", p)
    if len(rows) < want:                          # phase z: NULL sort values, keyset on parcel_id
        cl = clauses + [f"{col} IS NULL"]
        p = dict(params)
        if cur is not None and cur["p"] == "z":
            cl.append(f"parcel_id {cmp} %(_i)s::bigint")
            p.update(_i=cur["i"])
        rows += await fetchall(pool, f"SELECT {COLUMNS} FROM mv_parcel_metrics WHERE {' AND '.join(cl)} "
                                     f"ORDER BY parcel_id {direction} LIMIT {want - len(rows)}", p)

    items = rows[: body.limit]
    next_cursor = None
    if len(rows) > body.limit:
        last = items[-1]
        k = last[col]
        next_cursor = _encode({"f": fp, "p": "z" if k is None else "n", "k": None if k is None else str(k),
                               "i": last["parcel_id"], "t": total})
    return {"items": items, "next_cursor": next_cursor, "approx_total": total, "sort": col, "order": order}


OPTIONS_RANGES = """
SELECT min(area_sqm) AS area_sqm_min, max(area_sqm) AS area_sqm_max,
       min(price_sqm) AS price_sqm_min, max(price_sqm) AS price_sqm_max,
       min(cagr_5y) AS cagr_5y_min, max(cagr_5y) AS cagr_5y_max,
       min(nearest_active_project_m) AS active_project_m_min, max(nearest_active_project_m) AS active_project_m_max,
       min(nearest_highway_m) AS highway_m_min, max(nearest_highway_m) AS highway_m_max,
       min(soil_score) AS soil_score_min, max(soil_score) AS soil_score_max, count(*) AS parcels
FROM mv_parcel_metrics"""


@router.get("/screener/options")
async def screener_options(request: Request) -> dict:
    """Filter metadata: zones, land types, groundwater categories, mandals, value ranges and sorts (cached 5 min)."""
    cache = request.app.state.cache
    hit = cache.get("screener_options")
    if hit and hit[0] > time.monotonic():
        return hit[1]
    pool = request.app.state.pool
    out = {
        "filters": list(FRAGMENTS),
        "land_types": [t.value for t in LandType],
        "gw_categories": [g.value for g in GwCategory],
        "zones": await fetchall(pool, "SELECT zone_code, name FROM zone_type ORDER BY zone_code"),
        "mandals": await fetchall(pool, "SELECT mandal_id, name FROM mandal ORDER BY mandal_id"),
        "ranges": await fetchone(pool, OPTIONS_RANGES),
        "sorts": [{"sort": k, "default_order": v} for k, v in SORTS.items()],
        "max_limit": 100,
    }
    cache["screener_options"] = (time.monotonic() + OPTIONS_TTL_S, out)
    return out
