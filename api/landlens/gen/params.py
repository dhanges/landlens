"""Generator parameters (spec 2.12). Every value here is a modelling assumption unless marked otherwise.

Values marked PLACEHOLDER must be replaced before the report: spec 2.12 says the price base B "is calibrated to
published per-sq-yd ranges for Warangal, cited in the report".
"""

from __future__ import annotations

from datetime import date

# --- study area (DEC-004 starting box, UNVERIFIED; T-M1-8 confirms it and saves seed_inputs/study_area.geojson)
BBOX_LONLAT = (79.35, 17.75, 79.85, 18.15)  # min lon, min lat, max lon, max lat

# --- city centres for land type (spec 2.12 step 3). Approximate coordinates [assumption]; when the OSM export
# contains place nodes with these names, their coordinates are used instead.
CENTRES_LONLAT = {
    "Warangal": (79.5941, 17.9689),
    "Hanamkonda": (79.5584, 18.0072),
    "Kazipet": (79.5100, 17.9790),
}
URBAN_KM, PERI_KM = 4.0, 15.0      # spec 2.12 step 3
LAND_TYPE_NOISE_KM = 0.6           # "noise blurs the edges" [assumption]

# --- parcel sizes (spec 2.12 step 4): targets in sq m; the mean sets relative seed-point density
TARGET_SQM = {"urban_plot": (150, 500), "peri_urban": (200, 4000), "agricultural": (4000, 40000)}
PARCELS_PER_SF = 100_000           # SF1 = 100k, SF5 = 500k (spec 2.12)
MIN_PARCEL_SQM = 50.0              # slivers below this are dropped [assumption]

# --- demo window (DEC-004 shape; size computed per owner decision 2026-11-22): the core radius r and corridor
# half-width r * CORRIDOR_RATIO grow together until the expected parcel count at the spec 2.12 mean target
# sizes equals PARCELS_PER_SF * sf. Stored in parcel_coverage with the radii.
CORRIDOR_RATIO = 1 / 3
WINDOW_TOLERANCE = 0.002            # relative error on the expected count
CORRIDOR_PROJECTS = ("Mamnoor airport", "NH-163 corridor", "Outer Ring Road")  # "the Hyderabad highway" = NH-163 [assumption, T-M1-11 confirms]

ROAD_FRONTAGE_M = 15.0             # spec 2.12 step 5
ROAD_TYPES = ("national_highway", "state_highway", "major_road", "minor_road")

# --- price model (spec 2.12 step 8): P = B e^(-lambda d) G(t) prod_j(1 + a_j s_j(t) e^(-d_ij/tau_j)) (1 + beta f) eps
SQYD = 0.836127
B_INR_PER_SQM = {                  # PLACEHOLDER bases at the city core, replace with cited Warangal ranges
    "urban_plot": 25_000 / SQYD,   # ~Rs 25,000 per sq yd
    "peri_urban": 6_000 / SQYD,    # ~Rs 6,000 per sq yd
    "agricultural": 4_000_000 / 4046.86,  # ~Rs 40 lakh per acre
}
PRICE_BASE_YEAR = 2025            # B is the price level in this year (published ranges are current prices)
LAMBDA_PER_KM = 0.03
GROWTH = {"urban_plot": 0.07, "peri_urban": 0.09, "agricultural": 0.06}  # yearly, from 2010 [assumption]
GROWTH_SHOCK_SD = 0.02
VILLAGE_GROWTH_SD = 0.035          # per-village offset to the yearly growth rate, so 5-year growth varies by village
VILLAGE_GROWTH_CLIP = 0.08         # |offset| cap [assumption]
PROJECT_EFFECT = {                 # alpha_j, tau_j (km): uplift alpha at the project, decaying as e^(-d/tau) [assumption]
    "Mamnoor airport": (0.35, 4.0),
    "Inner Ring Road": (0.10, 1.5),
    "Outer Ring Road": (0.15, 2.0),
    "Kakatiya Mega Textile Park": (0.25, 3.0),
    "NH-163 corridor": (0.12, 2.0),
}
S_ANNOUNCED, S_SANCTIONED = 0.4, 1.0   # spec 2.12 step 8
BETA_PER_M = 0.004
EPS_SD = 0.15                      # log-normal noise

# --- sales (spec 2.12 step 9)
SALE_YEARS = range(2010, 2027)
SALE_CUTOFF = date(2026, 10, 31)   # fixed, so the same seed gives the same database regardless of today
SALE_RATE = {"urban_plot": 0.22, "peri_urban": 0.17, "agricultural": 0.10}  # per parcel-year [assumption]
PARTIAL_SHARE, PARTIAL_FRACTION = 0.10, (0.2, 0.8)
CONSIDERATION_SD = 0.08

# --- guideline rates (spec 2.12 step 10)
GUIDELINE_YEARS = (2010, 2013, 2016, 2019, 2022, 2025)
GUIDELINE_SHARE = (0.5, 0.8)

# --- environment (spec 2.12 step 11)
SOIL_GRID_M = 1000.0
GW_YEARS = range(2010, 2027)

# --- zones (spec 2.12 step 7)
ZONE_SEED_POINTS_PER_SF = 300

# --- demo account (DEC-003, OQ-24): re-created on every seed; local demo only
DEMO_EMAIL = "demo@landlens.local"
DEMO_PASSWORD = "demolandlens"      # documented in the README; change before any hosted deployment
DEMO_CREDITS = (("signup_bonus", 3), ("top_up", 7))
