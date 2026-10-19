-- When a serial was reported damaged (Report damage tab -> db.report_damage).
--
-- Needed by the Damage Report PDF export, whose time range filters on this
-- column. Additive and idempotent: a nullable column, no table rewrite, no
-- backfill. Serials flagged damaged before this column existed keep NULL
-- ("time unknown") -- the export lists them only when no time range is chosen.
--
-- Run once per database before using the new DataRework build.

ALTER TABLE public.staging_serial_data
    ADD COLUMN IF NOT EXISTS is_damaged_at timestamptz;
