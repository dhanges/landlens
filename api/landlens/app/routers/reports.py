"""GET /parcels/{id}/report (spec 2.9, 2.10): session required, and a report_unlock row for (user, parcel);
otherwise 402 report_locked."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..db import fetchone
from ..errors import ApiError
from ..security import require_user
from ..services import report
from .parcels import PARCEL_ID

router = APIRouter(tags=["reports"])

ACCESS = """
SELECT EXISTS (SELECT 1 FROM parcel WHERE parcel_id = %(pid)s) AS parcel,
       EXISTS (SELECT 1 FROM report_unlock WHERE user_id = %(uid)s AND parcel_id = %(pid)s) AS unlocked"""


@router.get("/parcels/{parcel_id}/report")
async def parcel_report(request: Request, parcel_id: int = PARCEL_ID, user_id: int = Depends(require_user)) -> dict:
    """The full report, conditional on land type; 402 report_locked until unlocked (POST /reports/{id}/unlock)."""
    pool = request.app.state.pool
    acc = await fetchone(pool, ACCESS, {"pid": parcel_id, "uid": user_id})
    if not acc["parcel"]:
        raise ApiError(404, "parcel_not_found", f"No parcel with id {parcel_id}.")
    if not acc["unlocked"]:
        raise ApiError(402, "report_locked", "Unlock this report for 1 credit to view it.")
    return await report.build(pool, parcel_id)
