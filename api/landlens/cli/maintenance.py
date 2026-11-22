"""`landlens refresh`, `landlens partitions`, `landlens verify`, `landlens checksum`."""

from __future__ import annotations

import os
import sys
from datetime import date

from landlens.db import connect

# dependency order (spec 2.6); mv_mandal_price_index per DEC-003 (OQ-20)
VIEWS = ("mv_village_price_index", "mv_parcel_metrics", "mv_mandal_price_index")
TARGET_SQM = {"urban_plot": (150, 500), "peri_urban": (200, 4000), "agricultural": (4000, 40000)}
GEOM_TABLES = ("district", "mandal", "village", "parcel", "parcel_coverage", "plan_zone", "infra_feature",
               "dev_project", "soil_sample")


def as_of() -> date:
    """AS_OF_DATE setting, default current_date (DEC-004, OQ-27)."""
    v = os.environ.get("AS_OF_DATE")
    return date.fromisoformat(v) if v else date.today()


def refresh() -> int:
    """REFRESH MATERIALIZED VIEW CONCURRENTLY in dependency order; exits non-zero on failure (spec 2.6, 2.14)."""
    with connect(autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT matviewname, ispopulated FROM pg_matviews WHERE schemaname = 'public'")
        present = dict(cur.fetchall())
        done = 0
        for v in VIEWS:
            if v not in present:
                continue
            mode = "CONCURRENTLY " if present[v] else ""   # first refresh of a WITH NO DATA view cannot be concurrent
            try:
                cur.execute(f"REFRESH MATERIALIZED VIEW {mode}{v}")
                done += 1
                print(f"  refreshed {v}{' (concurrently)' if mode else ''}")
            except Exception as exc:  # noqa: BLE001
                print(f"refresh failed on {v}: {exc}; the old view keeps serving", file=sys.stderr)
                return 1
    print(f"refresh: {done} view(s) refreshed" + ("" if done else " (no materialized views yet; created in M2)"))
    return 0


def partitions() -> int:
    """Create next year's sale_transaction partition ahead of time (spec 2.8, ADR-006); idempotent."""
    year = as_of().year + 1
    name = f"sale_transaction_{year}"
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (name,))
        if cur.fetchone()[0]:
            print(f"partitions: {name} already exists")
            return 0
        cur.execute("SELECT count(*) FROM sale_transaction_default WHERE registered_on >= %s AND registered_on < %s",
                    (date(year, 1, 1), date(year + 1, 1, 1)))
        if cur.fetchone()[0]:
            print(f"partitions: rows for {year} sit in the DEFAULT partition; move them first", file=sys.stderr)
            return 1
        cur.execute(f"CREATE TABLE {name} PARTITION OF sale_transaction FOR VALUES FROM (%s) TO (%s)",
                    (date(year, 1, 1), date(year + 1, 1, 1)))
    print(f"partitions: created {name}")
    return 0


def verify() -> int:
    """M1 done-when: row counts per table, zero spatial-consistency failures, zero invalid geometries,
    and a point query returns a parcel. Exits non-zero if any of those fail."""
    ok = True
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
                         AND c.relname NOT IN ('spatial_ref_sys', 'schema_migrations') ORDER BY 1""")
        tables = [r[0] for r in cur.fetchall()]
        print(f"row counts ({len(tables)} tables):")
        for t in tables:
            cur.execute(f"SELECT count(*) FROM {t}")
            print(f"  {t:<24} {cur.fetchone()[0]:>10,}")
        cur.execute("""SELECT count(*) FROM parcel p JOIN village v USING (village_id)
                       WHERE NOT ST_Within(p.centroid, v.geom)""")
        spatial = cur.fetchone()[0]
        print(f"spatial-consistency failures (parcel centroid outside its village): {spatial}")
        ok &= spatial == 0
        invalid = 0
        for t in GEOM_TABLES:
            cur.execute(f"SELECT count(*) FROM {t} WHERE NOT ST_IsValid(geom)")
            invalid += cur.fetchone()[0]
        print(f"invalid geometries across {len(GEOM_TABLES)} geometry tables: {invalid}")
        ok &= invalid == 0
        cur.execute("""SELECT p.parcel_id, v.name, p.land_type, round(p.area_sqm) FROM parcel p JOIN village v USING (village_id)
                       WHERE ST_Contains(p.geom, ST_Transform(ST_SetSRID(ST_MakePoint(79.5941, 17.9689), 4326), 32644))""")
        hit = cur.fetchone()
        print("point query at Warangal centre (79.5941 E, 17.9689 N): "
              + (f"parcel {hit[0]} in {hit[1]}, {hit[2]}, {hit[3]} sq m" if hit else "NO PARCEL"))
        ok &= hit is not None
        print("parcel area by land type (sq m) vs spec 2.12 targets:")
        cur.execute("""SELECT land_type, count(*), round(percentile_cont(0.5) WITHIN GROUP (ORDER BY area_sqm)),
                              round(percentile_cont(0.1) WITHIN GROUP (ORDER BY area_sqm)),
                              round(percentile_cont(0.9) WITHIN GROUP (ORDER BY area_sqm))
                       FROM parcel GROUP BY 1 ORDER BY 1""")
        for lt, n, med, p10, p90 in cur.fetchall():
            lo, hi = TARGET_SQM[lt]
            print(f"  {lt:<13} n={n:>7,}  median {med:>8,}  p10-p90 {p10:,}-{p90:,}  (target {lo:,}-{hi:,})")
        cur.execute("""SELECT 'infra_feature', source::text, count(*) FROM infra_feature GROUP BY 2
                       UNION ALL SELECT 'dev_project', source::text, count(*) FROM dev_project GROUP BY 2
                       UNION ALL SELECT 'village names', CASE WHEN name LIKE '[fallback]%%' THEN 'fallback' ELSE 'real' END,
                                        count(*) FROM village GROUP BY 2 ORDER BY 1, 2""")
        print("provenance: " + "; ".join(f"{t} {s}={n}" for t, s, n in cur.fetchall()))
        cur.execute("""SELECT scale_factor, core_radius_m, corridor_halfwidth_m, expected_parcels,
                              round((ST_Area(geom) / 1e6)::numeric, 1) FROM parcel_coverage ORDER BY 1""")
        for sf, r, h, e, a in cur.fetchall():
            print(f"parcel window SF{sf}: core radius {r} m, corridor half-width {h} m, {a} sq km, "
                  f"expected {e:,} parcels at target sizes")
        cur.execute("""SELECT u.email, u.credit_balance, coalesce(sum(l.delta), 0) FROM app_user u
                       LEFT JOIN credit_ledger l USING (user_id) WHERE u.email = 'demo@landlens.local'
                       GROUP BY u.email, u.credit_balance""")
        demo = cur.fetchone()
        print("demo account: " + (f"{demo[0]}, balance {demo[1]}, ledger sum {demo[2]}" if demo else "MISSING"))
        ok &= demo is not None and demo[1] == demo[2]
        cur.execute("SELECT count(*) FROM sale_transaction_default")
        d = cur.fetchone()[0]
        print(f"rows in DEFAULT sale partition (should be 0): {d}")
        ok &= d == 0
    print("VERIFY OK" if ok else "VERIFY FAILED")
    return 0 if ok else 1


def checksum() -> int:
    """Per-table content checksums (excluding timestamps), to prove same seed + SF = same database."""
    queries = {
        "village": "SELECT md5(string_agg(concat_ws('|', village_id, mandal_id, name, geom), ',' ORDER BY village_id)) FROM village",
        "parcel": "SELECT md5(string_agg(concat_ws('|', parcel_id, village_id, survey_no, land_type, geom, road_frontage_m), ',' ORDER BY parcel_id)) FROM parcel",
        "sale_transaction": "SELECT md5(string_agg(concat_ws('|', txn_id, registered_on, parcel_id, consideration_inr, area_sqm, doc_no), ',' ORDER BY txn_id)) FROM sale_transaction",
        "guideline_rate": "SELECT md5(string_agg(concat_ws('|', village_id, land_class, effective_from, rate_inr_per_sqm), ',' ORDER BY village_id, land_class, effective_from)) FROM guideline_rate",
        "plan_zone": "SELECT md5(string_agg(concat_ws('|', zone_id, zone_code, geom), ',' ORDER BY zone_id)) FROM plan_zone",
        "parcel_zone": "SELECT md5(string_agg(concat_ws('|', parcel_id, zone_id, overlap_pct), ',' ORDER BY parcel_id, zone_id)) FROM parcel_zone",
        "soil_sample": "SELECT md5(string_agg(concat_ws('|', sample_id, sampled_on, ph, organic_carbon_pct, n_kg_ha, texture, geom), ',' ORDER BY sample_id)) FROM soil_sample",
        "gw_assessment": "SELECT md5(string_agg(concat_ws('|', mandal_id, assessment_year, extraction_pct), ',' ORDER BY mandal_id, assessment_year)) FROM gw_assessment",
    }
    with connect() as conn, conn.cursor() as cur:
        for t, q in queries.items():
            cur.execute(q)
            print(f"{t:<18} {cur.fetchone()[0]}")
    return 0
