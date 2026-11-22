"""The hand-built 10-parcel fixture (spec 2.16) with known answers.

Coordinates are metre offsets from an origin near Warangal in EPSG:32644 (ADR-004), so distances can be read off.

    district  [-1000,-1000]-[9000,5000]   (the area outside both villages is outside the study area)
    mandal 1 = village 101 "Hanamkonda" [0,0]-[4000,4000]
    mandal 2 = village 102 "Kazipet"    [4000,0]-[8000,4000]
    parcel window (parcel_coverage SF1)   [0,0]-[6000,4000]
    zones R [0,1450] x [0,4000], C [1450,4000] x [0,4000], A [4000,8000] x [0,4000]
    J1 ring road y = 1500 (sanctioned 2023-06-01: active); J2 airport (shelved 2024: not active);
    J3 urban scheme (first status 2027-01-01, after the as-of date: not active). Highway y = 500.

    id village type          box (x0,y0,x1,y1)        survey  frontage  sales (date: INR per sq m)
    1  101     peri_urban    1000,1000,1100,1100      1       20        2019-06-01: 4000, 2025-03-01: 6000
    2  101     peri_urban    1200,1000,1300,1100      2                 2024-06-01: 5000
    3  101     peri_urban    1400,1000,1600,1100      3                 2025-06-01: 4500   (R 25%, C 75%)
    4  101     peri_urban    1000,1300,1100,1400      4                 2022-01-01: 3000
    5  101     peri_urban    3000,3000,3100,3100      5                 2026-01-10: 7000
    6  101     urban_plot    1700,1000,1750,1040      6/A               2025-02-01: 20000
    7  101     urban_plot    1800,1000,1850,1040      6/B               2023-01-01: 18000
    8  101     agricultural  2000,2000,2300,2300      8                 2024-05-01: 800
    9  102     peri_urban    5000,1000,5100,1100      1                 2024-09-01: 5500
    10 102     agricultural  5500,1000,5700,1200      10                2021-03-01: 600, 2025-05-01: 900
"""

from __future__ import annotations

OX, OY = 350000, 1985000
AS_OF = "2026-11-25"


def box(x0, y0, x1, y1) -> str:
    return f"ST_MakeEnvelope({OX + x0}, {OY + y0}, {OX + x1}, {OY + y1}, 32644)"


def mbox(*a) -> str:
    return f"ST_Multi({box(*a)})"


def pt(x, y) -> str:
    return f"ST_SetSRID(ST_MakePoint({OX + x}, {OY + y}), 32644)"


def line(*xy) -> str:
    coords = ", ".join(f"{OX + x} {OY + y}" for x, y in xy)
    return f"ST_GeomFromText('LINESTRING({coords})', 32644)"


PARCELS = [
    # id, village, type, box, survey, sub_div, frontage
    (1, 101, "peri_urban", (1000, 1000, 1100, 1100), "1", "", 20),
    (2, 101, "peri_urban", (1200, 1000, 1300, 1100), "2", "", 0),
    (3, 101, "peri_urban", (1400, 1000, 1600, 1100), "3", "", 0),
    (4, 101, "peri_urban", (1000, 1300, 1100, 1400), "4", "", 0),
    (5, 101, "peri_urban", (3000, 3000, 3100, 3100), "5", "", 0),
    (6, 101, "urban_plot", (1700, 1000, 1750, 1040), "6", "A", 0),
    (7, 101, "urban_plot", (1800, 1000, 1850, 1040), "6", "B", 0),
    (8, 101, "agricultural", (2000, 2000, 2300, 2300), "8", "", 0),
    (9, 102, "peri_urban", (5000, 1000, 5100, 1100), "1", "", 0),
    (10, 102, "agricultural", (5500, 1000, 5700, 1200), "10", "", 0),
]
SALES = [  # parcel_id, date, price per sq m (full-parcel sales)
    (1, "2019-06-01", 4000), (1, "2025-03-01", 6000), (2, "2024-06-01", 5000), (3, "2025-06-01", 4500),
    (4, "2022-01-01", 3000), (5, "2026-01-10", 7000), (6, "2025-02-01", 20000), (7, "2023-01-01", 18000),
    (8, "2024-05-01", 800), (9, "2024-09-01", 5500), (10, "2021-03-01", 600), (10, "2025-05-01", 900),
]


def statements() -> list[str]:
    s = [
        f"INSERT INTO district VALUES (1, 'Test District', {mbox(-1000, -1000, 9000, 5000)}, 'synthetic')",
        f"INSERT INTO mandal VALUES (1, 1, 'Alpha Mandal', {mbox(0, 0, 4000, 4000)}, 'synthetic'),"
        f" (2, 1, 'Beta Mandal', {mbox(4000, 0, 8000, 4000)}, 'synthetic')",
        f"INSERT INTO village (village_id, mandal_id, name, lgd_code, geom, boundary_source) VALUES"
        f" (101, 1, 'Hanamkonda', 9101, {mbox(0, 0, 4000, 4000)}, 'osm'),"
        f" (102, 2, 'Kazipet', 9102, {mbox(4000, 0, 8000, 4000)}, 'synthetic')",
        f"INSERT INTO parcel_coverage VALUES (1, {mbox(0, 0, 6000, 4000)}, 'synthetic')",
    ]
    rows = ", ".join(f"({i}, {v}, '{sn}', '{sd}', '{t}', {box(*b)}, {fr}, 'synthetic')"
                     for i, v, t, b, sn, sd, fr in PARCELS)
    s.append("INSERT INTO parcel (parcel_id, village_id, survey_no, sub_div, land_type, geom, road_frontage_m, source)"
             f" OVERRIDING SYSTEM VALUE VALUES {rows}")
    area = {i: (b[2] - b[0]) * (b[3] - b[1]) for i, _, _, b, *_ in PARCELS}
    rows = ", ".join(f"('{d}', {p}, {price * area[p]}, {area[p]}, 'DOC-{n}', 'synthetic')"
                     for n, (p, d, price) in enumerate(SALES, 1))
    s.append(f"INSERT INTO sale_transaction (registered_on, parcel_id, consideration_inr, area_sqm, doc_no, source)"
             f" VALUES {rows}")
    s += [
        "INSERT INTO document (document_id, title, doc_type, issued_by, issued_on, file_path, sha256, page_count)"
        " OVERRIDING SYSTEM VALUE VALUES (1, 'G.O.Ms.No.202', 'government_order', 'MA&UD', '2024-11-01',"
        " 'seed_inputs/docs/go202.pdf', repeat('a', 64), 40)",
        "INSERT INTO master_plan VALUES (1, 'Test Master Plan 2041', 'KUDA', 2041, NULL, NULL)",
        "INSERT INTO zone_type VALUES ('R', 'Residential', 'Dwellings', NULL, NULL),"
        " ('C', 'Commercial', 'Shops and offices', 1, 12), ('A', 'Agricultural', 'Farming', NULL, NULL)",
        f"INSERT INTO plan_zone (zone_id, plan_id, zone_code, geom, source) OVERRIDING SYSTEM VALUE VALUES"
        f" (1, 1, 'R', {mbox(0, 0, 1450, 4000)}, 'synthetic'), (2, 1, 'C', {mbox(1450, 0, 4000, 4000)}, 'real'),"
        f" (3, 1, 'A', {mbox(4000, 0, 8000, 4000)}, 'synthetic')",
        # the same derivation as gen/load.py derive()
        "INSERT INTO parcel_zone (parcel_id, zone_id, overlap_pct) SELECT parcel_id, zone_id, LEAST(100, round(pct, 2))"
        " FROM (SELECT p.parcel_id, z.zone_id, (100 * ST_Area(ST_Intersection(p.geom, z.geom)) / ST_Area(p.geom))::numeric"
        " AS pct FROM parcel p JOIN plan_zone z ON ST_Intersects(p.geom, z.geom)) s WHERE round(pct, 2) > 0",
        f"INSERT INTO infra_feature (feature_type, name, geom, source) VALUES"
        f" ('national_highway', 'NH test', {line((0, 500), (8000, 500))}, 'osm'),"
        f" ('water_body', 'Test tank', {box(2400, 2000, 2600, 2300)}, 'osm')",
        f"INSERT INTO dev_project (project_id, name, project_type, geom, expected_completion, source)"
        f" OVERRIDING SYSTEM VALUE VALUES"
        f" (1, 'Test Ring Road', 'ring_road', {line((0, 1500), (8000, 1500))}, '2028-12-31', 'real'),"
        f" (2, 'Test Airport', 'airport', {box(7000, 3000, 7500, 3500)}, NULL, 'synthetic'),"
        f" (3, 'Future Scheme', 'urban_scheme', {pt(1050, 900)}, NULL, 'synthetic')",
        "INSERT INTO project_status_history VALUES (1, '2020-01-01', 'proposed', 'synthetic'),"
        " (1, '2023-06-01', 'sanctioned', 'real'), (2, '2021-01-01', 'proposed', 'synthetic'),"
        " (2, '2024-01-01', 'shelved', 'synthetic'), (3, '2027-01-01', 'sanctioned', 'synthetic')",
        "INSERT INTO parcel_project_impact (parcel_id, project_id, distance_m)"
        " SELECT p.parcel_id, j.project_id, round(ST_Distance(p.centroid, j.geom)::numeric, 1)"
        " FROM parcel p CROSS JOIN dev_project j WHERE ST_DWithin(p.centroid, j.geom, 10000)",
        f"INSERT INTO soil_sample (sampled_on, ph, organic_carbon_pct, n_kg_ha, p_kg_ha, k_kg_ha, texture, geom, source)"
        f" VALUES ('2023-01-01', 6.5, 1.00, 400, 40, 400, 'loam', {pt(1050, 1200)}, 'synthetic'),"
        f" ('2023-01-01', 8.5, 0.50, 200, 20, 200, 'clay', {pt(2150, 2400)}, 'synthetic'),"
        f" ('2023-01-01', 7.0, 0.75, 300, 30, 300, 'sandy loam', {pt(5600, 1500)}, 'synthetic'),"
        f" ('2023-01-01', 6.0, 0.20, 100, 10, 100, 'sand', {pt(3000, 500)}, 'synthetic')",
        "INSERT INTO gw_assessment (mandal_id, assessment_year, extraction_pct, source) VALUES"
        " (1, 2022, 65.0, 'synthetic'), (1, 2024, 95.0, 'synthetic'), (2, 2024, 120.0, 'synthetic')",
        "INSERT INTO guideline_rate VALUES (101, 'peri_urban', '2020-01-01', 2000, 'synthetic'),"
        " (101, 'peri_urban', '2024-04-01', 3000, 'synthetic'), (101, 'urban_plot', '2024-04-01', 10000, 'synthetic'),"
        " (101, 'agricultural', '2020-01-01', 300, 'synthetic'), (102, 'peri_urban', '2020-01-01', 2500, 'synthetic'),"
        " (102, 'agricultural', '2020-01-01', 400, 'synthetic')",
    ]
    return s
