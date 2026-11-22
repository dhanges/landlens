-- 009: as-of date (DEC-004, OQ-27). Schema phase.
-- Executable by PUBLIC (function default); it only reads a setting.
-- "Today" for the views and queries: the landlens.as_of_date setting when set (landlens refresh sets it from
-- AS_OF_DATE; fixtures and the determinism test pin 2026-11-25), otherwise current_date.
CREATE FUNCTION landlens_as_of() RETURNS date
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT coalesce(nullif(current_setting('landlens.as_of_date', true), '')::date, current_date)
$$;
