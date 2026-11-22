"""Free routes on the fixture with known answers: health, errors, search, /parcels/at, summary, screener, trends."""

from __future__ import annotations

import pytest

from .fixture import OX, OY


def lonlat(owner, x, y):
    return owner.execute("SELECT ST_X(g), ST_Y(g) FROM (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 32644),"
                         " 4326) AS g) s", (OX + x, OY + y)).fetchone()


def test_health_and_error_shape(client):
    h = client.get("/api/health").json()
    assert h["db"] == "ok" and h["openai"] in ("ok", "degraded")
    r = client.get("/api/nowhere")
    assert r.status_code == 404 and r.json() == {"error": {"code": "not_found", "message": "Not Found"}}
    r = client.delete("/api/health")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"
    assert "server-timing" in r.headers


def test_connects_as_api_role(owner, client):
    client.get("/api/health")
    users = {r[0] for r in owner.execute("SELECT usename FROM pg_stat_activity WHERE application_name = 'landlens_api'"
                                         " AND datname = current_database()")}
    assert users == {"landlens_api"}


def test_search_villages_and_survey_numbers(client):
    v = client.get("/api/search", params={"q": "Hanmakonda"}).json()      # FR-2 transliteration variant
    assert [x["village_id"] for x in v["villages"]] == [101] and v["villages"][0]["mandal"] == "Alpha Mandal"
    assert isinstance(v["villages"][0]["lat"], float) and isinstance(v["villages"][0]["lon"], float)
    assert client.get("/api/search", params={"q": "kazi"}).json()["villages"][0]["name"] == "Kazipet"
    assert sorted(p["parcel_id"] for p in client.get("/api/search", params={"q": "1"}).json()["parcels"]) == [1, 9]
    within = client.get("/api/search", params={"q": "1", "village_id": 102}).json()["parcels"]
    assert [p["parcel_id"] for p in within] == [9]
    hit = client.get("/api/search", params={"q": "6/B"}).json()["parcels"]
    assert [p["parcel_id"] for p in hit] == [7] and isinstance(hit[0]["lat"], float)
    assert [p["parcel_id"] for p in client.get("/api/search", params={"q": "6"}).json()["parcels"]] == [6, 7]
    assert client.get("/api/search", params={"q": "100%_"}).json() == {"villages": [], "parcels": []}
    assert client.get("/api/search", params={"q": ""}).status_code == 422
    assert client.get("/api/search", params={"q": "x", "limit": 51}).status_code == 422


@pytest.mark.parametrize("xy,code", [((1150, 1050), "no_parcel_at_point"), ((7000, 1000), "outside_parcel_window"),
                                     ((-500, -500), "outside_coverage")])
def test_parcels_at_404s(client, owner, xy, code):
    lon, lat = lonlat(owner, *xy)
    r = client.get("/api/parcels/at", params={"lat": lat, "lon": lon})
    assert r.status_code == 404 and r.json()["error"]["code"] == code


def test_parcels_at_and_summary(client, owner):
    lon, lat = lonlat(owner, 1050, 1050)
    s = client.get("/api/parcels/at", params={"lat": lat, "lon": lon}).json()
    assert s["parcel_id"] == 1 and s["village"] == "Hanamkonda" and s["land_type"] == "peri_urban"
    assert s["area_sqm"] == 10000 and s["zone_code"] == "R" and s["unlocked"] is False
    assert s["village_median_sqm"] == 5500        # median of 5000, 6000, 4500, 7000 (36 months to 2026-11-25)
    assert s["nearest_active_project_m"] == 450 and s["nearest_active_project"] == "Test Ring Road"
    assert s["price_vs_median_pct"] == pytest.approx(100 * (6000 / 5500 - 1), abs=0.01)
    assert s["geometry"]["type"] == "Polygon" and len(s["geometry"]["coordinates"][0]) == 5
    assert s["zone_name"] is not None
    assert client.get("/api/parcels/3/summary").json()["zone_code"] == "C"     # 75% C beats 25% R
    assert client.get("/api/parcels/at", params={"lat": 95, "lon": 0}).status_code == 422
    r = client.get("/api/parcels/999/summary")
    assert r.status_code == 404 and r.json()["error"]["code"] == "parcel_not_found"
    assert client.get("/api/parcels/abc/summary").status_code == 422


def test_metrics_view_known_answers(owner):
    rows = {r[0]: r[1:] for r in owner.execute(
        "SELECT parcel_id, nearest_active_project_m, nearest_highway_m, cagr_5y, gw_category::text, price_sqm "
        "FROM mv_parcel_metrics")}
    assert rows[1][0] == 450 and rows[4][0] == 150 and rows[5][0] == 1550        # only J1 is active as of the date
    assert rows[1][1] == 550
    assert float(rows[1][2]) == pytest.approx((7000 / 3000) ** 0.25 - 1, abs=1e-4)   # 2026 vs base 2022 (+-1 of 2021)
    assert rows[9][2] is None                                                       # V102 peri: no base year
    assert rows[1][3] == "critical" and rows[9][3] == "over_exploited"
    assert rows[4][4] == 3000                                                       # last sale, any age


def screen(client, **body):
    r = client.post("/api/screener", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_screener_filters_sort_and_keyset_with_nulls(client):
    f = {"land_type": "peri_urban", "max_active_project_m": 1000}
    pages, cursor = [], None
    while True:
        d = screen(client, filters=f, limit=2, **({"cursor": cursor} if cursor else {}))
        pages.append([i["parcel_id"] for i in d["items"]])
        assert d["approx_total"] == 5
        cursor = d["next_cursor"]
        if not cursor:
            break
    assert pages == [[4, 3], [2, 1], [9]]          # cagr ties broken by parcel_id DESC, NULL cagr (P9) last
    d = screen(client, filters=f, sort="price_sqm")
    assert [i["parcel_id"] for i in d["items"]] == [4, 3, 2, 9, 1]
    assert [i["parcel_id"] for i in screen(client, filters=f, sort="price_sqm", order="desc")["items"]] == [1, 9, 2, 3, 4]
    assert [i["parcel_id"] for i in screen(client, filters=f, sort="area_sqm", limit=1)["items"]] == [3]
    near = screen(client, filters=f, sort="nearest_active_project_m")["items"]
    assert near[0]["parcel_id"] == 4


def test_screener_each_filter(client):
    ids = lambda d: sorted(i["parcel_id"] for i in d["items"])  # noqa: E731
    assert ids(screen(client, filters={"land_type": "peri_urban", "zone_code": ["C"]})) == [3, 5]
    assert ids(screen(client, filters={"land_type": "peri_urban", "exclude_gw": ["over_exploited"]})) == [1, 2, 3, 4, 5]
    assert ids(screen(client, filters={"area_sqm_min": 40000})) == [8, 10]
    assert ids(screen(client, filters={"area_sqm_max": 2000})) == [6, 7]
    assert ids(screen(client, filters={"price_sqm_min": 18000})) == [6, 7]
    assert ids(screen(client, filters={"land_type": "peri_urban", "price_sqm_max": 4500})) == [3, 4]
    assert ids(screen(client, filters={"max_highway_m": 600})) == [1, 2, 3, 6, 7, 9, 10]
    assert ids(screen(client, filters={"min_cagr_5y": 0.2, "land_type": "peri_urban"})) == [1, 2, 3, 4, 5]
    assert ids(screen(client, filters={"mandal_id": [2]})) == [9, 10]
    # price vs village median: P1 +9.1%, P2 -9.1%, P3 -18.2%, P4 -45.5%, P5 +27.3% (median 5500); P9 0% (102)
    assert ids(screen(client, filters={"land_type": "peri_urban", "max_price_vs_median_pct": 0})) == [2, 3, 4, 9]
    row = next(i for i in screen(client, filters={"land_type": "peri_urban"})["items"] if i["parcel_id"] == 4)
    assert row["survey_no"] == "4" and row["sub_div"] == "" and isinstance(row["lat"], float)
    assert row["price_vs_median_pct"] == pytest.approx(100 * (3000 / 5500 - 1), abs=0.01)
    assert ids(screen(client, filters={"zone_code[]": ["A"]})) == [9, 10]           # spec 2.9 spelling accepted
    high = screen(client, filters={"min_soil_score": 60})["items"]
    assert high and all(i["soil_score"] >= 60 for i in high)
    assert screen(client, filters={"land_type": "urban_plot", "zone_code": ["A"]}) == {
        "items": [], "next_cursor": None, "approx_total": 0, "sort": "cagr_5y", "order": "desc"}


def test_screener_rejects_unknown_and_bad_input(client):
    for body in ({"filters": {"owner_name": "x"}}, {"filters": {}, "limit": 101}, {"sort": "parcel_id"},
                 {"filters": {"land_type": "forest"}}, {"filters": {"mandal_id": [70000]}}, {"extra": 1},
                 {"filters": {"zone_code": "R; DROP TABLE parcel"}}):
        r = client.post("/api/screener", json=body)
        assert r.status_code == 422, body
    first = screen(client, filters={"land_type": "peri_urban"}, limit=1)
    r = client.post("/api/screener", json={"filters": {"land_type": "agricultural"}, "cursor": first["next_cursor"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_cursor"     # cursor bound to its filters
    r = client.post("/api/screener", json={"cursor": "!!!"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_cursor"


def test_screener_options(client):
    o = client.get("/api/screener/options").json()
    assert [z["zone_code"] for z in o["zones"]] == ["A", "C", "R"]
    assert o["ranges"]["parcels"] == 10 and o["ranges"]["area_sqm_max"] == 90000
    assert {s["sort"] for s in o["sorts"]} == {"cagr_5y", "price_sqm", "area_sqm", "nearest_active_project_m"}
    assert len(o["filters"]) == 13 and [m["mandal_id"] for m in o["mandals"]] == [1, 2]


def test_village_trend_gaps_and_guideline(client):
    d = client.get("/api/trends/villages/101", params={"land_type": "peri_urban"}).json()
    s = d["series"]
    assert [x["yr"] for x in s] == [2019, 2022, 2024, 2025, 2026]
    assert [x["yoy_base_yr"] for x in s] == [None, 2019, 2022, 2024, 2025]      # gaps are visible (spec 2.14)
    assert [x["median_price_sqm"] for x in s] == [4000, 3000, 5000, 5250, 7000]
    assert [x["n_sales"] for x in s] == [1, 1, 1, 2, 1]
    assert s[0]["yoy"] is None and s[1]["yoy"] == pytest.approx(-0.25) and s[2]["yoy"] == pytest.approx(0.6667)
    assert [x["guideline_sqm"] for x in s] == [None, 2000, 3000, 3000, 3000]   # rate in force on 31 Dec


def test_trend_defaults_and_mandal(client):
    d = client.get("/api/trends/villages/101").json()
    assert d["land_type"] == "peri_urban" and d["mandal_id"] == 1                # most sales in the village
    m = client.get("/api/trends/mandals/1", params={"land_type": "peri_urban"}).json()
    assert [x["median_price_sqm"] for x in m["series"]] == [4000, 3000, 5000, 5250, 7000]
    m2 = client.get("/api/trends/mandals/2", params={"land_type": "agricultural"}).json()
    assert [(x["yr"], x["yoy_base_yr"], x["guideline_sqm"]) for x in m2["series"]] == [(2021, None, 400), (2025, 2021, 400)]
    assert client.get("/api/trends/villages/101", params={"land_type": "forest"}).status_code == 422
    r = client.get("/api/trends/villages/999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "village_not_found"
    assert client.get("/api/trends/mandals/9").status_code == 404
