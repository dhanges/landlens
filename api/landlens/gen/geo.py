"""Geometry helpers. All projection work is done by PostGIS (EPSG:4326 -> EPSG:32644, ADR-004)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import shapely
from shapely.geometry import box, shape

from . import params

SRID = 32644


def seed_inputs() -> Path:
    return Path(os.environ.get("LANDLENS_SEED_INPUTS", "/app/seed_inputs"))


def to_utm(conn, geoms_lonlat: list) -> list:
    """Transform shapely geometries from lon/lat to UTM 44N in one round trip."""
    if not geoms_lonlat:
        return []
    wkb = [shapely.to_wkb(g, hex=False) for g in geoms_lonlat]
    with conn.cursor() as cur:
        cur.execute(
            """SELECT ST_AsBinary(ST_Transform(ST_SetSRID(ST_GeomFromWKB(g), 4326), %s))
               FROM unnest(%s::bytea[]) WITH ORDINALITY AS t(g, i) ORDER BY i""",
            (SRID, wkb),
        )
        return [shapely.from_wkb(bytes(r[0])) for r in cur.fetchall()]


def study_area(conn) -> tuple[object, str]:
    """Study area in UTM and a description of where it came from (DEC-004)."""
    f = seed_inputs() / "study_area.geojson"
    if f.exists():
        data = json.loads(f.read_text())
        feats = data.get("features", [data])
        geom = shapely.union_all([shape(x.get("geometry", x)) for x in feats])
        return to_utm(conn, [geom])[0], str(f)
    minx, miny, maxx, maxy = params.BBOX_LONLAT
    return to_utm(conn, [box(minx, miny, maxx, maxy)])[0], "DEC-004 starting box (UNVERIFIED estimate)"
