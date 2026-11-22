"""Valuation and report on the fixture (FR-6, FR-7; spec 2.14 widening; DEC-003 OQ-18/OQ-22)."""

from __future__ import annotations

import math
import statistics
import uuid
from datetime import date

import pytest

from landlens.app.services import valuation as V


def unlock(client, h, pid):
    r = client.post(f"/api/reports/{pid}/unlock", headers={**h, "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    return r.json()


def test_report_requires_session_and_unlock(client, make_user):
    r = client.get("/api/parcels/1/report")
    assert r.status_code == 401 and r.json()["error"]["code"] == "auth_required"
    h, _ = make_user()
    r = client.get("/api/parcels/1/report", headers=h)
    assert r.status_code == 402 and r.json()["error"]["code"] == "report_locked"
    assert client.get("/api/parcels/999/report", headers=h).status_code == 404
    assert client.get("/api/parcels/1/summary", headers=h).json()["unlocked"] is False
    unlock(client, h, 1)
    assert client.get("/api/parcels/1/summary", headers=h).json()["unlocked"] is True
    assert client.get("/api/parcels/1/report", headers=h).status_code == 200


def expected_p1() -> list[float]:
    """Spec 2.14 widening for parcel 1: 4 comparables within 5 km / 36 months (P2, P3, P5, P9) -> widen to
    10 km / 60 months, which adds P4 (2022). Adjust each to P1 (10,000 sq m, frontage, 450 m from J1)."""
    t_v101 = {2022: 7000 / 3000, 2024: 7000 / 5000, 2025: 7000 / 5250, 2026: 1.0}   # village 101 index to 2026
    comps = [  # price, area, d_project, sale year, time factor
        (5000, 10000, 450, t_v101[2024]),    # P2
        (3000, 10000, 150, t_v101[2022]),    # P4
        (4500, 20000, 450, t_v101[2025]),    # P3
        (7000, 10000, 1550, t_v101[2026]),   # P5
        (5500, 10000, 450, 1.0),             # P9, village 102: only 2024 data, so index 2024 -> 2024
    ]
    out = []
    for price, area, dproj, tf in comps:
        f = (10000 / area) ** -0.10 * 1.05 * math.exp(-0.02 * (450 - dproj) / 1000) * tf
        out.append(price * f)
    return out


def test_valuation_widened_low_confidence(client, make_user):
    h, _ = make_user()
    unlock(client, h, 1)
    rep = client.get("/api/parcels/1/report", headers=h).json()
    v = rep["valuation"]
    assert v["confidence"] == "low" and v["n_comparables"] == 5
    assert v["search_radius_m"] == 10000 and v["search_months"] == 60
    assert [c["parcel_id"] for c in rep["comparables"]] == [2, 4, 3, 5, 9]           # KNN order
    assert [c["distance_m"] for c in rep["comparables"]] == [200, 300, 450, pytest.approx(2828.4, abs=0.1), 4000]
    exp = sorted(expected_p1())
    q = statistics.quantiles(exp, n=4, method="inclusive")
    assert v["p25_sqm"] == pytest.approx(q[0], abs=0.01)
    assert v["p50_sqm"] == pytest.approx(q[1], abs=0.01) == pytest.approx(exp[2], abs=0.01)
    assert v["p75_sqm"] == pytest.approx(q[2], abs=0.01)
    assert v["p50_inr"] == round(q[1] * 10000)
    drivers = {d["factor"]: d["median_effect_pct"] for d in v["drivers"]}
    assert drivers == {"area": 0.0, "frontage": 5.0, "project": 0.0, "time": pytest.approx(33.33, abs=0.01)}
    assert v["locality_median_sqm"] == 5500


def test_valuation_none_under_three(client, make_user):
    h, _ = make_user()
    unlock(client, h, 6)
    v = client.get("/api/parcels/6/report", headers=h).json()["valuation"]
    assert v["confidence"] == "none" and v["n_comparables"] == 1            # only P7 (2023) within 60 months
    assert v["p50_sqm"] is None and v["p25_sqm"] is None and v["drivers"] == []
    assert v["locality_median_sqm"] == 20000


def test_confidence_rules():
    assert V.confidence(10, False, 1500) == "high"
    assert V.confidence(10, False, 2500) == "medium"
    assert V.confidence(7, True, 500) == "low"
    assert V.confidence(2, True, 100) == "none" and V.confidence(0, False, None) == "none"


def test_adjust_factors_unit():
    s = V.Subject(1, "peri_urban", 1000.0, 10.0, 2000.0, None)
    c = V.Comp(2, 7, 4000.0, 0.0, 12000.0, date(2024, 3, 1), 1000.0, 100.0)
    V.adjust(s, [c], {(7, 2024): 800.0, (7, 2026): 1000.0}, {7: 2026})
    assert c.factors["area"] == pytest.approx(0.25 ** -0.1)
    assert c.factors["frontage"] == pytest.approx(1.05)
    assert c.factors["project"] == pytest.approx(math.exp(-0.02 * (2000 - 10000) / 1000))   # comp capped at 10 km
    assert c.factors["time"] == pytest.approx(1.25)
    assert c.adjusted_price_sqm == pytest.approx(1000 * math.prod(c.factors.values()))


def test_report_sections_agricultural_first_and_soil(client, make_user):
    h, _ = make_user()
    unlock(client, h, 8)
    rep = client.get("/api/parcels/8/report", headers=h).json()
    assert rep["section_order"][0] == "environment" and list(rep)[3] == "environment"
    env = rep["environment"]
    assert env["groundwater"]["latest_category"] == "critical"
    assert [(g["assessment_year"], g["category"]) for g in env["groundwater"]["trend"]] == [(2022, "safe"),
                                                                                             (2024, "critical")]
    assert len(env["soil"]["nearest_samples"]) == 3 and env["soil"]["soil_score"] is not None
    assert rep["location"]["distances_m"]["water"] == 250
    assert rep["price_history"][0]["price_sqm"] == 800


def test_report_urban_plot_has_no_soil(client, make_user):
    h, _ = make_user()
    unlock(client, h, 6)
    rep = client.get("/api/parcels/6/report", headers=h).json()
    assert rep["section_order"][:3] == ["location", "zoning", "environment"]
    assert "soil" not in rep["environment"] and "groundwater" in rep["environment"]
    assert rep["provenance"]["soil"] == []


def test_report_zoning_location_history_provenance(client, make_user):
    h, _ = make_user()
    unlock(client, h, 3)
    unlock(client, h, 1)
    z = client.get("/api/parcels/3/report", headers=h).json()["zoning"]
    assert z["primary_zone"] == "C" and z["overlap_pct"] == 75
    assert [(x["zone_code"], x["overlap_pct"]) for x in z["zones"]] == [("C", 75), ("R", 25)]
    assert z["source_clause"] == {"document_id": 1, "title": "G.O.Ms.No.202", "page": 12}
    rep = client.get("/api/parcels/1/report", headers=h).json()
    assert rep["zoning"]["source_clause"] == {"document_id": None,
                                              "note": "summarised from the KUDA land-use map legend"}
    loc = rep["location"]
    assert loc["village"] == "Hanamkonda" and loc["mandal"] == "Alpha Mandal" and loc["district"] == "Test District"
    assert loc["distances_m"] == {"highway": 550, "water": pytest.approx(loc["distances_m"]["water"]),
                                  "active_project": 450}
    assert loc["nearest_active_project"] == {"project_id": 1, "name": "Test Ring Road"}
    statuses = {p["name"]: p["status"] for p in loc["projects_within_10km"]}
    assert statuses == {"Test Ring Road": "sanctioned", "Test Airport": "shelved", "Future Scheme": None}
    assert [s["registered_on"] for s in rep["price_history"]] == ["2019-06-01", "2025-03-01"]
    assert [s["median_price_sqm"] for s in rep["locality_trend"]["series"]] == [4000, 3000, 5000, 5250, 7000]
    prov = rep["provenance"]
    assert prov["village_boundary"] == "osm" and prov["parcel"] == "synthetic"
    assert "parcel" in prov["synthetic_fields"] and "village_boundary" not in prov["synthetic_fields"]
    assert prov["projects"] == ["real", "synthetic"]
