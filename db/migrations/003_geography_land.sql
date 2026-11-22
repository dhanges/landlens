-- Migration 003: geography and land tables (spec 2.4, groups 1-2).
-- Applied by `landlens migrate` (spec 2.17) as landlens_owner.
-- All geometry is EPSG:32644 (UTM 44N, meters) per ADR-004.
-- Provenance (FR-12, DEC-004 / OQ-03, OQ-37): district, mandal and village carry
-- boundary_source; parcel carries source. district.boundary_source is a DEC-004
-- addition extending the provenance rule to every geography table.
-- Indexes are deferred to M2.

-- 1. Geography
CREATE TABLE district (
  district_id smallint PRIMARY KEY,
  name        text NOT NULL UNIQUE,
  geom        geometry(MultiPolygon,32644) NOT NULL,
  boundary_source data_source NOT NULL);

CREATE TABLE mandal (
  mandal_id   smallint PRIMARY KEY,
  district_id smallint NOT NULL REFERENCES district,
  name        text NOT NULL,
  geom        geometry(MultiPolygon,32644) NOT NULL,
  boundary_source data_source NOT NULL,
  UNIQUE (district_id, name));

CREATE TABLE village (
  village_id      integer PRIMARY KEY,
  mandal_id       smallint NOT NULL REFERENCES mandal,
  name            text NOT NULL,
  lgd_code        integer UNIQUE,
  geom            geometry(MultiPolygon,32644) NOT NULL,
  centroid        geometry(Point,32644) GENERATED ALWAYS AS (ST_PointOnSurface(geom)) STORED,
  boundary_source data_source NOT NULL);

-- 2. Land
CREATE TABLE parcel (
  parcel_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  village_id      integer NOT NULL REFERENCES village,
  survey_no       text NOT NULL,
  sub_div         text NOT NULL DEFAULT '',
  land_type       land_type NOT NULL,
  geom            geometry(Polygon,32644) NOT NULL,
  area_sqm        numeric(12,2) GENERATED ALWAYS AS (ST_Area(geom)) STORED,
  centroid        geometry(Point,32644) GENERATED ALWAYS AS (ST_PointOnSurface(geom)) STORED,
  road_frontage_m numeric(8,2) NOT NULL DEFAULT 0 CHECK (road_frontage_m >= 0),
  source          data_source NOT NULL DEFAULT 'synthetic',
  UNIQUE (village_id, survey_no, sub_div));   -- real-world candidate key

-- parcel_coverage: the 23rd table approved by DEC-004 (OQ-37); the union of the
-- synthetic parcel fabric per scale factor, used to clip and tile coverage.
CREATE TABLE parcel_coverage (
  scale_factor smallint PRIMARY KEY,
  geom         geometry(MultiPolygon,32644) NOT NULL,
  source       data_source NOT NULL DEFAULT 'synthetic');
