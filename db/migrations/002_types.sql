-- Migration 002: enum types (spec 2.4).
-- Applied by `landlens migrate` (spec 2.17) as landlens_owner.
CREATE TYPE land_type      AS ENUM ('urban_plot','peri_urban','agricultural');
CREATE TYPE data_source    AS ENUM ('real','osm','synthetic');
CREATE TYPE project_status AS ENUM ('proposed','sanctioned','under_construction','completed','shelved');
CREATE TYPE gw_category    AS ENUM ('safe','semi_critical','critical','over_exploited');
CREATE TYPE doc_type       AS ENUM ('master_plan','government_order','notification','regulation');
CREATE TYPE feature_type   AS ENUM ('national_highway','state_highway','major_road','minor_road','rail',
                                    'water_body','river','school','hospital','industrial_area','airport','bus_station');
CREATE TYPE project_type   AS ENUM ('ring_road','highway','airport','industrial_park','rail','urban_scheme');
CREATE TYPE ledger_reason  AS ENUM ('signup_bonus','top_up','report_unlock','refund');
