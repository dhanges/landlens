"""Load and derive (spec 2.12 step 12, ingestion path of spec 2.11).

Small tables are COPYed directly. Parcels and sales go through UNLOGGED staging tables, then one transaction of
INSERT ... ON CONFLICT DO UPDATE with a SAVEPOINT per 10k-row batch, so one bad batch is logged and skipped.
The loader applies ST_MakeValid, rejects geometry that is still invalid, and rejects any parcel whose centroid is
not within its village (spec 2.5 spatial consistency). parcel_zone and parcel_project_impact are derived in SQL.
"""

from __future__ import annotations

import numpy as np
import shapely

from .geo import SRID
from .steps import LAND_TYPES, World

BATCH = 10_000
DATA_TABLES = ("parcel_zone", "parcel_project_impact", "watchlist", "report_unlock", "credit_ledger", "app_user",
               "sale_transaction", "guideline_rate", "parcel", "parcel_coverage", "plan_zone", "zone_type",
               "master_plan", "document_chunk", "document", "project_status_history", "dev_project", "infra_feature",
               "soil_sample", "gw_assessment", "village", "mandal", "district")


def ewkb(g) -> str:
    return shapely.to_wkb(shapely.set_srid(g, SRID), hex=True, include_srid=True)


def copy_rows(cur, table: str, cols: tuple, rows) -> int:
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
        for r in rows:
            cp.write_row(r)
            n += 1
    return n


def reset(conn) -> None:
    """A seed is a full reset of generated and app data (the demo account is re-created by the seed)."""
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE")
        cur.execute("ALTER SEQUENCE sale_txn_seq RESTART WITH 1")


def load_reference(conn, w: World) -> dict:
    stats = {}
    with conn.cursor() as cur:
        stats["district"] = copy_rows(cur, "district", ("district_id", "name", "geom", "boundary_source"),
                                      ((d["district_id"], d["name"], ewkb(d["geom"]), d["boundary_source"]) for d in w.districts))
        stats["mandal"] = copy_rows(cur, "mandal", ("mandal_id", "district_id", "name", "geom", "boundary_source"),
                                    ((m["mandal_id"], m["district_id"], m["name"], ewkb(m["geom"]), m["boundary_source"])
                                     for m in w.mandals))
        stats["village"] = copy_rows(cur, "village", ("village_id", "mandal_id", "name", "geom", "boundary_source"),
                                     ((v["village_id"], v["mandal_id"], v["name"], ewkb(v["geom"]), v["boundary_source"])
                                      for v in w.villages))
        seen_osm = set()

        def infra():
            for ft, name, osm_id, g, src in w.layers.features:
                if osm_id is not None:
                    if osm_id in seen_osm:
                        continue
                    seen_osm.add(osm_id)
                yield (ft, name, osm_id, ewkb(g), src)
        stats["infra_feature"] = copy_rows(cur, "infra_feature", ("feature_type", "name", "osm_id", "geom", "source"), infra())
        # projects need their generated ids for the status histories
        ids = []
        for p in w.projects:
            cur.execute("""INSERT INTO dev_project (name, project_type, geom, expected_completion, source)
                           VALUES (%s, %s, %s::geometry, %s, %s) RETURNING project_id""",
                        (p.name, p.project_type, ewkb(p.geom), p.expected_completion, p.source))
            ids.append(cur.fetchone()[0])
        stats["dev_project"] = len(ids)
        stats["project_status_history"] = copy_rows(
            cur, "project_status_history", ("project_id", "effective_from", "status", "source"),
            ((pid, d, st, src) for pid, p in zip(ids, w.projects, strict=True) for d, st, src in p.statuses))
        cur.execute("""INSERT INTO master_plan (plan_id, name, authority, horizon_year, approved_on, document_id)
                       VALUES (1, 'KUDA Master Plan 2041', 'Kakatiya Urban Development Authority', 2041, NULL, NULL)""")
        stats["master_plan"] = 1
        stats["zone_type"] = copy_rows(cur, "zone_type", ("zone_code", "name", "permitted_uses"), w.zone_types)
        stats["plan_zone"] = copy_rows(cur, "plan_zone", ("plan_id", "zone_code", "geom", "source"),
                                       ((1, c, ewkb(g), "synthetic") for c, g in w.plan_zones))
        m = w.window_meta
        cur.execute("""INSERT INTO parcel_coverage (scale_factor, geom, source, core_radius_m, corridor_halfwidth_m,
                                                    expected_parcels)
                       VALUES (%s, %s::geometry, 'synthetic', %s, %s, %s)""",
                    (max(1, int(round(w.sf))), ewkb(w.window), m["core_radius_m"], m["corridor_halfwidth_m"],
                     m["expected_parcels"]))
        stats["soil_sample"] = copy_rows(
            cur, "soil_sample",
            ("sampled_on", "ph", "organic_carbon_pct", "n_kg_ha", "p_kg_ha", "k_kg_ha", "texture", "geom", "source"),
            ((*s[:7], ewkb(s[7]), "synthetic") for s in w.soil))
        stats["gw_assessment"] = copy_rows(cur, "gw_assessment", ("mandal_id", "assessment_year", "extraction_pct", "source"),
                                           ((m, y, e, "synthetic") for m, y, e in w.gw))
        stats["guideline_rate"] = copy_rows(cur, "guideline_rate",
                                            ("village_id", "land_class", "effective_from", "rate_inr_per_sqm", "source"),
                                            ((v, t, d, r, "synthetic") for v, t, d, r in w.guideline))
    return stats


def _batched_upsert(conn, total: int, sql: str, label: str) -> tuple[int, list]:
    failed = []
    with conn.cursor() as cur:
        for lo in range(0, total, BATCH):
            hi = lo + BATCH
            cur.execute("SAVEPOINT batch")
            try:
                cur.execute(sql, {"lo": lo, "hi": hi})
                cur.execute("RELEASE SAVEPOINT batch")
            except Exception as exc:  # noqa: BLE001 - one bad batch is logged and skipped (spec 2.11)
                cur.execute("ROLLBACK TO SAVEPOINT batch")
                failed.append((lo, hi, str(exc).splitlines()[0]))
                print(f"  {label}: batch {lo}-{hi} skipped: {failed[-1][2]}")
    return total, failed


def load_parcels(conn, w: World) -> dict:
    P = w.parcels
    with conn.cursor() as cur:
        cur.execute("""CREATE UNLOGGED TABLE IF NOT EXISTS stg_parcel (
                         seq int PRIMARY KEY, village_id int, survey_no text, sub_div text, land_type land_type,
                         geom geometry, road_frontage_m numeric(8,2), source data_source)""")
        cur.execute("TRUNCATE stg_parcel")
        copy_rows(cur, "stg_parcel", ("seq", "village_id", "survey_no", "sub_div", "land_type", "geom", "road_frontage_m", "source"),
                  ((i, int(P["village_id"][i]), P["survey_no"][i], "", LAND_TYPES[int(P["land_type"][i])], ewkb(P["geom"][i]),
                    float(P["frontage"][i]), "synthetic") for i in range(len(P["geom"]))))
        cur.execute("UPDATE stg_parcel SET geom = ST_MakeValid(geom) WHERE NOT ST_IsValid(geom)")
        repaired = cur.rowcount
        cur.execute("""SELECT count(*) FILTER (WHERE NOT ST_IsValid(s.geom) OR GeometryType(s.geom) <> 'POLYGON'),
                              count(*) FILTER (WHERE ST_IsValid(s.geom) AND GeometryType(s.geom) = 'POLYGON'
                                               AND NOT ST_Within(ST_PointOnSurface(s.geom), v.geom))
                       FROM stg_parcel s JOIN village v USING (village_id)""")
        invalid, inconsistent = cur.fetchone()
    total, failed = _batched_upsert(conn, len(P["geom"]), """
        INSERT INTO parcel (village_id, survey_no, sub_div, land_type, geom, road_frontage_m, source)
        SELECT s.village_id, s.survey_no, s.sub_div, s.land_type, s.geom, s.road_frontage_m, s.source
        FROM stg_parcel s JOIN village v USING (village_id)
        WHERE s.seq >= %(lo)s AND s.seq < %(hi)s
          AND ST_IsValid(s.geom) AND GeometryType(s.geom) = 'POLYGON'
          AND ST_Within(ST_PointOnSurface(s.geom), v.geom)
        ORDER BY s.seq
        ON CONFLICT (village_id, survey_no, sub_div) DO UPDATE
          SET land_type = EXCLUDED.land_type, geom = EXCLUDED.geom,
              road_frontage_m = EXCLUDED.road_frontage_m, source = EXCLUDED.source""", "parcel")
    return {"staged": total, "repaired_make_valid": repaired, "rejected_invalid": invalid,
            "rejected_spatial": inconsistent, "failed_batches": len(failed)}


def load_sales(conn, w: World) -> dict:
    S, P = w.sales, w.parcels
    with conn.cursor() as cur:
        cur.execute("""CREATE UNLOGGED TABLE IF NOT EXISTS stg_sale (
                         txn_id bigint PRIMARY KEY, registered_on date, village_id int, survey_no text,
                         consideration_inr numeric(14,2), area_sqm numeric(12,2), doc_no text)""")
        cur.execute("TRUNCATE stg_sale")
        vid = P["village_id"][S["parcel_idx"]]
        sno = P["survey_no"][S["parcel_idx"]]
        copy_rows(cur, "stg_sale", ("txn_id", "registered_on", "village_id", "survey_no", "consideration_inr", "area_sqm", "doc_no"),
                  ((int(S["txn_id"][i]), S["date"][i], int(vid[i]), sno[i], float(S["consideration"][i]),
                    float(S["area"][i]), f"{S['date'][i].year}/{int(vid[i]):03d}/{int(S['txn_id'][i]):07d}")
                   for i in range(len(S["txn_id"]))))
    total, failed = _batched_upsert(conn, int(len(S["txn_id"])), """
        INSERT INTO sale_transaction (txn_id, registered_on, parcel_id, consideration_inr, area_sqm, doc_no, source)
        SELECT s.txn_id, s.registered_on, p.parcel_id, s.consideration_inr, s.area_sqm, s.doc_no, 'synthetic'
        FROM stg_sale s JOIN parcel p ON p.village_id = s.village_id AND p.survey_no = s.survey_no AND p.sub_div = ''
        WHERE s.txn_id > %(lo)s AND s.txn_id <= %(hi)s
        ON CONFLICT (txn_id, registered_on) DO UPDATE
          SET parcel_id = EXCLUDED.parcel_id, consideration_inr = EXCLUDED.consideration_inr,
              area_sqm = EXCLUDED.area_sqm, doc_no = EXCLUDED.doc_no""", "sale")
    with conn.cursor() as cur:
        cur.execute("SELECT setval('sale_txn_seq', GREATEST((SELECT max(txn_id) FROM sale_transaction), 1))")
        cur.execute("DROP TABLE IF EXISTS stg_parcel, stg_sale")
    return {"staged": total, "failed_batches": len(failed)}


def derive(conn) -> dict:
    """parcel_zone (largest-overlap logic lives in the views) and parcel_project_impact within 10 km (spec 2.4)."""
    with conn.cursor() as cur:
        # temporary index on the small side only; the real indexes come in migration 010 (post-load)
        cur.execute("CREATE INDEX tmp_plan_zone_gix ON plan_zone USING gist (geom)")
        cur.execute("""INSERT INTO parcel_zone (parcel_id, zone_id, overlap_pct)
                       SELECT parcel_id, zone_id, LEAST(100, round(pct, 2)) FROM (
                         SELECT p.parcel_id, z.zone_id,
                                (100 * ST_Area(ST_Intersection(p.geom, z.geom)) / ST_Area(p.geom))::numeric AS pct
                         FROM parcel p JOIN plan_zone z ON ST_Intersects(p.geom, z.geom)) s
                       WHERE round(pct, 2) > 0""")
        pz = cur.rowcount
        cur.execute("DROP INDEX tmp_plan_zone_gix")
        cur.execute("""INSERT INTO parcel_project_impact (parcel_id, project_id, distance_m)
                       SELECT p.parcel_id, j.project_id, round(ST_Distance(p.centroid, j.geom)::numeric, 1)
                       FROM parcel p CROSS JOIN dev_project j
                       WHERE ST_DWithin(p.centroid, j.geom, 10000)""")
        ppi = cur.rowcount
    return {"parcel_zone": pz, "parcel_project_impact": ppi}


def summary_counts(arr) -> dict:
    vals, counts = np.unique(arr, return_counts=True)
    return {LAND_TYPES[int(v)]: int(c) for v, c in zip(vals, counts, strict=True)}


def demo_account(conn) -> dict:
    """DEC-003 (OQ-24): demo account with 10 credits as ledger rows, so balance = SUM(ledger.delta)."""
    from argon2 import PasswordHasher  # argon2id by default (spec 2.10)

    from . import params

    total = sum(d for _, d in params.DEMO_CREDITS)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO app_user (email, password_hash, credit_balance) VALUES (%s, %s, %s)
                       RETURNING user_id""", (params.DEMO_EMAIL, PasswordHasher().hash(params.DEMO_PASSWORD), total))
        uid = cur.fetchone()[0]
        for reason, delta in params.DEMO_CREDITS:
            cur.execute("INSERT INTO credit_ledger (user_id, delta, reason) VALUES (%s, %s, %s)", (uid, delta, reason))
    return {"email": params.DEMO_EMAIL, "user_id": uid, "credits": total}
