-- Migration 004: documents/master plan, infrastructure/projects and environment
-- tables (spec 2.4, groups 3-5).
-- Applied by `landlens migrate` (spec 2.17) as landlens_owner.
-- All geometry is EPSG:32644 (UTM 44N, meters) per ADR-004.
-- Provenance (FR-12, DEC-004 / OQ-03): plan_zone, infra_feature, soil_sample and
-- gw_assessment carry source; dev_project.source with hand-digitized geometry =
-- 'real'; project_status_history.source with sourced date = 'real', else
-- 'synthetic'. Derived tables parcel_zone and parcel_project_impact carry no
-- provenance column.
-- Delete rules (spec 2.5 / DEC-004 / OQ-04): ON DELETE CASCADE for document_chunk,
-- parcel_zone, project_status_history and parcel_project_impact; gw_assessment.
-- mandal_id keeps the default NO ACTION.
-- DEC-003 (OQ-22): zone_type carries source_document_id and source_page, filled
-- when zone types are loaded from the master plan (T-M1-12); NULL means permitted
-- uses were summarised from the land-use map legend (DEC-005).
-- Indexes are deferred to M2.

-- 3. Documents (RAG) and master plan
CREATE TABLE document (
  document_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title       text NOT NULL,
  doc_type    doc_type NOT NULL,
  issued_by   text NOT NULL,
  issued_on   date,
  source_url  text,
  file_path   text NOT NULL,
  sha256      char(64) NOT NULL UNIQUE,     -- re-ingesting the same PDF is a no-op
  page_count  integer NOT NULL CHECK (page_count > 0),
  ingested_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE document_chunk (                -- weak entity of document
  document_id integer REFERENCES document ON DELETE CASCADE,
  chunk_no    integer,
  page_start  integer NOT NULL,
  page_end    integer NOT NULL CHECK (page_end >= page_start),
  content     text NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  embedding   vector(1536) NOT NULL,
  PRIMARY KEY (document_id, chunk_no));

CREATE TABLE master_plan (
  plan_id      smallint PRIMARY KEY,
  name         text NOT NULL,
  authority    text NOT NULL,
  horizon_year smallint NOT NULL,
  approved_on  date,
  document_id  integer REFERENCES document);

CREATE TABLE zone_type (
  zone_code      text PRIMARY KEY,
  name           text NOT NULL,
  permitted_uses text NOT NULL,
  -- DEC-003 (OQ-22): source clause stored at load time; NULL means the permitted
  -- uses were summarised from the land-use map legend (DEC-005).
  source_document_id integer REFERENCES document,
  source_page        integer CHECK (source_page > 0));

CREATE TABLE plan_zone (
  zone_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  plan_id   smallint NOT NULL REFERENCES master_plan,
  zone_code text NOT NULL REFERENCES zone_type,
  geom      geometry(MultiPolygon,32644) NOT NULL,
  source    data_source NOT NULL);

CREATE TABLE parcel_zone (                   -- M:N, derived by spatial join
  parcel_id   bigint  REFERENCES parcel    ON DELETE CASCADE,
  zone_id     integer REFERENCES plan_zone ON DELETE CASCADE,
  overlap_pct numeric(5,2) NOT NULL CHECK (overlap_pct > 0 AND overlap_pct <= 100),
  PRIMARY KEY (parcel_id, zone_id));

-- 4. Infrastructure and development projects
CREATE TABLE infra_feature (
  feature_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  feature_type feature_type NOT NULL,
  name         text,
  osm_id       bigint UNIQUE,
  geom         geometry(Geometry,32644) NOT NULL,
  source       data_source NOT NULL);

CREATE TABLE dev_project (
  project_id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name                text NOT NULL UNIQUE,
  project_type        project_type NOT NULL,
  geom                geometry(Geometry,32644) NOT NULL,
  expected_completion date,
  document_id         integer REFERENCES document,
  source              data_source NOT NULL);   -- hand-digitized geometry = 'real'

CREATE TABLE project_status_history (        -- temporal: status as of any date
  project_id     integer REFERENCES dev_project ON DELETE CASCADE,
  effective_from date,
  status         project_status NOT NULL,
  source         data_source NOT NULL,      -- sourced date = 'real', else 'synthetic'
  PRIMARY KEY (project_id, effective_from));

CREATE TABLE parcel_project_impact (         -- M:N with attribute, within 10 km
  parcel_id  bigint  REFERENCES parcel      ON DELETE CASCADE,
  project_id integer REFERENCES dev_project ON DELETE CASCADE,
  distance_m numeric(9,1) NOT NULL,
  PRIMARY KEY (parcel_id, project_id));

-- 5. Environment
CREATE TABLE soil_sample (
  sample_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sampled_on         date NOT NULL,
  ph                 numeric(3,1) CHECK (ph BETWEEN 0 AND 14),
  organic_carbon_pct numeric(4,2),
  n_kg_ha numeric(6,1), p_kg_ha numeric(6,1), k_kg_ha numeric(6,1),
  texture            text,
  geom               geometry(Point,32644) NOT NULL,
  source             data_source NOT NULL);

-- gw_assessment.mandal_id keeps the default NO ACTION (DEC-004 / OQ-04).
CREATE TABLE gw_assessment (
  mandal_id       smallint REFERENCES mandal,
  assessment_year smallint,
  extraction_pct  numeric(5,1) NOT NULL CHECK (extraction_pct >= 0),
  category        gw_category GENERATED ALWAYS AS (
                    CASE WHEN extraction_pct <= 70  THEN 'safe'::gw_category
                         WHEN extraction_pct <= 90  THEN 'semi_critical'::gw_category
                         WHEN extraction_pct <= 100 THEN 'critical'::gw_category
                         ELSE 'over_exploited'::gw_category END) STORED,
  source          data_source NOT NULL,
  PRIMARY KEY (mandal_id, assessment_year));
