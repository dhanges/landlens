"""Locality trends (FR-5, spec 2.9; DEC-003 OQ-11/OQ-20).

Series items: {yr, median_price_sqm, p25_price_sqm, p75_price_sqm, n_sales, yoy, yoy_base_yr, guideline_sqm}
(p25/p75: the spread of sale prices that year, migration 015). Years without sales are gaps;
yoy compares to the previous year with data (the views' lag), and yoy_base_yr names that year, so a gap shows
as yoy_base_yr < yr - 1 (spec 2.14). Years after the as-of date are excluded.
guideline_sqm is the rate in force at the end of the year (latest effective_from <= 31 Dec); for a mandal it is
the median of its villages' rates.
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from ..db import fetchall

VILLAGE_SERIES = """
SELECT i.yr, round(i.median_price_sqm::numeric, 2) AS median_price_sqm, i.n_sales,
       round(i.yoy::numeric, 4) AS yoy, lag(i.yr) OVER (ORDER BY i.yr) AS yoy_base_yr,
       round(i.p25_price_sqm::numeric, 2) AS p25_price_sqm, round(i.p75_price_sqm::numeric, 2) AS p75_price_sqm,
       (SELECT g.rate_inr_per_sqm FROM guideline_rate g
        WHERE g.village_id = i.village_id AND g.land_class = i.land_type AND g.effective_from <= make_date(i.yr, 12, 31)
        ORDER BY g.effective_from DESC LIMIT 1) AS guideline_sqm
FROM mv_village_price_index i
WHERE i.village_id = %(id)s AND i.land_type = %(lt)s::land_type AND i.yr <= extract(year FROM landlens_as_of())
ORDER BY i.yr"""

MANDAL_SERIES = """
SELECT i.yr, round(i.median_price_sqm::numeric, 2) AS median_price_sqm, i.n_sales,
       round(i.yoy::numeric, 4) AS yoy, lag(i.yr) OVER (ORDER BY i.yr) AS yoy_base_yr,
       round(i.p25_price_sqm::numeric, 2) AS p25_price_sqm, round(i.p75_price_sqm::numeric, 2) AS p75_price_sqm,
       (SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY r.rate)::numeric, 2)
        FROM village v
        CROSS JOIN LATERAL (SELECT g.rate_inr_per_sqm AS rate FROM guideline_rate g
                            WHERE g.village_id = v.village_id AND g.land_class = i.land_type
                              AND g.effective_from <= make_date(i.yr, 12, 31)
                            ORDER BY g.effective_from DESC LIMIT 1) r
        WHERE v.mandal_id = i.mandal_id) AS guideline_sqm
FROM mv_mandal_price_index i
WHERE i.mandal_id = %(id)s AND i.land_type = %(lt)s::land_type AND i.yr <= extract(year FROM landlens_as_of())
ORDER BY i.yr"""

DEFAULT_TYPE = {
    "village": "SELECT land_type::text FROM mv_village_price_index WHERE village_id = %(id)s "
               "GROUP BY 1 ORDER BY sum(n_sales) DESC, 1 LIMIT 1",
    "mandal": "SELECT land_type::text FROM mv_mandal_price_index WHERE mandal_id = %(id)s "
              "GROUP BY 1 ORDER BY sum(n_sales) DESC, 1 LIMIT 1",
}


async def default_land_type(pool: AsyncConnectionPool, level: str, id_: int) -> str | None:
    rows = await fetchall(pool, DEFAULT_TYPE[level], {"id": id_})
    return rows[0]["land_type"] if rows else None


async def series(pool: AsyncConnectionPool, level: str, id_: int, land_type: str) -> list[dict]:
    q = VILLAGE_SERIES if level == "village" else MANDAL_SERIES
    return await fetchall(pool, q, {"id": id_, "lt": land_type})
