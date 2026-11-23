"""POST /chat and GET /documents/{id}/file (spec 2.9, 2.13; FR-8).

/chat needs a session (spec 2.10) and is rate-limited to 20 per minute per IP and per user (in memory, per
worker). The pipeline lives in services/rag.py. Optional parcel_id adds the parcel's zone and land type as
context for the answer (never as a citable source).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ..db import fetchone
from ..errors import ApiError
from ..ratelimit import client_ip
from ..security import require_user
from ..services import rag

router = APIRouter(tags=["chat"])


class ChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=500)
    parcel_id: int | None = Field(None, ge=1, le=2**63 - 1)


class Citation(BaseModel):
    n: int
    document_id: int
    title: str
    page_start: int
    page_end: int
    snippet: str


class ChatResponse(BaseModel):
    found: bool
    degraded: bool
    answer: str | None
    citations: list[Citation]
    note: str | None = None


PARCEL_CONTEXT = """
SELECT p.land_type::text AS land_type, zt.name AS zone_name, v.name AS village
FROM parcel p JOIN village v USING (village_id)
LEFT JOIN mv_parcel_metrics pm USING (parcel_id) LEFT JOIN zone_type zt ON zt.zone_code = pm.zone_code
WHERE p.parcel_id = %s"""


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatBody, request: Request, user_id: int = Depends(require_user)) -> dict:
    """Answer from the ingested documents with numbered citations, or "not found in the documents"."""
    lim = request.app.state.chat_limiter
    lim.hit(("ip", client_ip(request)))
    lim.hit(("user", user_id))
    pool = request.app.state.pool
    context = None
    if body.parcel_id is not None:
        p = await fetchone(pool, PARCEL_CONTEXT, (body.parcel_id,))
        if p is None:
            raise ApiError(404, "parcel_not_found", f"No parcel with id {body.parcel_id}.")
        zone = (p["zone_name"] or "unknown zone").replace("[fallback] ", "")
        context = f"The user is asking about a {p['land_type'].replace('_', ' ')} parcel in {zone} zone."
    s = request.app.state.settings
    return await rag.answer(pool, request.app.state.llm, body.question.strip(), s.chat_max_distance, context)


@router.get("/documents/{document_id}/file", tags=["documents"])
async def document_file(request: Request, document_id: int = PathParam(ge=1, le=2**31 - 1)) -> FileResponse:
    """The source PDF, inline, so the browser's viewer can open it at #page=N."""
    row = await fetchone(request.app.state.pool, "SELECT title, file_path FROM document WHERE document_id = %s",
                         (document_id,))
    if row is None:
        raise ApiError(404, "document_not_found", f"No document with id {document_id}.")
    root = Path(request.app.state.settings.seed_inputs).resolve()
    path = (root / row["file_path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ApiError(404, "document_file_missing", "The document's file is not available on this server.")
    safe = "".join(ch for ch in row["title"] if ch.isalnum() or ch in " ,.()-")[:120].strip() or "document"
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{safe}.pdf"',
                                 "Cache-Control": "public, max-age=86400"})
