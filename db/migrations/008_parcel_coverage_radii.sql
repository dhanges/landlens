-- 008: record how the demo window was sized (owner decision 2026-11-22). Schema phase.
-- The window's core radius and corridor half-width are computed so that the expected parcel count at the
-- spec 2.12 target sizes equals the scale factor's target; verify reports them.
ALTER TABLE parcel_coverage
  ADD COLUMN core_radius_m        numeric(8,1) CHECK (core_radius_m > 0),
  ADD COLUMN corridor_halfwidth_m numeric(8,1) CHECK (corridor_halfwidth_m > 0),
  ADD COLUMN expected_parcels     integer      CHECK (expected_parcels > 0);
