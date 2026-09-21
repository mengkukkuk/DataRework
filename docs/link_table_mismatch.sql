-- Why some containers list nothing inside them in the Delete dialog.
--
-- The card in the Container manager counts what is in filling_product_logs.
-- The dialog's "Inside this container" list reads staging_product_logs (the
-- link table). When the two disagree, the card shows "2 inside" and the dialog
-- shows nothing. These queries say which containers disagree, and why.
--
-- All read-only. Run them against the live database; nothing here writes.

-- 1. Displays whose saved rows exist but that the link table does not know at
--    all: no link of their own, and nothing linked under them. These are the
--    ones that list nothing and report "0 link(s) will be deleted".
SELECT f.display_serial_no,
       count(*)                          AS saved_rows,
       count(DISTINCT f.unit_serial_no)  AS units
FROM public.filling_product_logs f
WHERE f.display_serial_no IS NOT NULL
  AND f.display_serial_no <> ''
  AND NOT EXISTS (SELECT 1 FROM public.staging_product_logs e
                  WHERE e.serial_no = f.display_serial_no::text
                    AND e.serial_label_code = 'display')
  AND NOT EXISTS (SELECT 1 FROM public.staging_product_logs e
                  WHERE e.parent_serial_no = f.display_serial_no::text
                    AND e.parent_serial_label_code = 'display')
GROUP BY f.display_serial_no
ORDER BY f.display_serial_no;

-- 2. Same question for inners and cartons, as one count per level.
SELECT 'inner' AS level, count(DISTINCT f.inner_serial_no) AS containers_without_links
FROM public.filling_product_logs f
WHERE f.inner_serial_no IS NOT NULL AND f.inner_serial_no <> ''
  AND NOT EXISTS (SELECT 1 FROM public.staging_product_logs e
                  WHERE e.serial_no = f.inner_serial_no::text AND e.serial_label_code = 'inner')
  AND NOT EXISTS (SELECT 1 FROM public.staging_product_logs e
                  WHERE e.parent_serial_no = f.inner_serial_no::text
                    AND e.parent_serial_label_code = 'inner')
UNION ALL
SELECT 'carton', count(DISTINCT f.carton_serial_no)
FROM public.filling_product_logs f
WHERE f.carton_serial_no IS NOT NULL AND f.carton_serial_no <> ''
  AND NOT EXISTS (SELECT 1 FROM public.staging_product_logs e
                  WHERE e.parent_serial_no = f.carton_serial_no::text
                    AND e.parent_serial_label_code = 'carton');

-- 3. Is it really absent, or is it there under a different spelling?
--    This finds links that match once both sides are trimmed but not before --
--    i.e. a stored serial with leading/trailing whitespace. If this returns
--    rows, the data is not missing, it is padded, and the fix is to trim the
--    link table (or to compare with btrim() in the queries).
SELECT DISTINCT e.serial_label_code,
       e.serial_no                AS link_table_value,
       '[' || e.serial_no || ']'  AS shown_with_brackets,
       length(e.serial_no)        AS stored_length,
       length(btrim(e.serial_no)) AS trimmed_length
FROM public.staging_product_logs e
WHERE e.serial_no IS NOT NULL
  AND e.serial_no <> btrim(e.serial_no)
ORDER BY e.serial_label_code, link_table_value
LIMIT 50;

-- 4. The same check for the parent side of a link.
SELECT DISTINCT e.parent_serial_label_code,
       '[' || e.parent_serial_no || ']' AS shown_with_brackets,
       length(e.parent_serial_no)       AS stored_length
FROM public.staging_product_logs e
WHERE e.parent_serial_no IS NOT NULL
  AND e.parent_serial_no <> btrim(e.parent_serial_no)
LIMIT 50;

-- 5. Saved rows naming a link id that no longer exists. These are the
--    "N saved row reference(s) named a link that no longer existed" entries in
--    the app's Log window, and they are what used to abort a container delete.
SELECT count(*) FILTER (WHERE f.unit_source_id IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM public.staging_product_logs e
                                          WHERE e.id = f.unit_source_id))    AS stale_unit_refs,
       count(*) FILTER (WHERE f.display_source_id IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM public.staging_product_logs e
                                          WHERE e.id = f.display_source_id)) AS stale_display_refs,
       count(*) FILTER (WHERE f.inner_source_id IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM public.staging_product_logs e
                                          WHERE e.id = f.inner_source_id))   AS stale_inner_refs,
       count(*)                                                              AS rows_total
FROM public.filling_product_logs f;

-- 6. One specific container, end to end -- change the serial and read the four
--    numbers together: saved rows, its own link, links under it, stale refs.
WITH target AS (SELECT 'D26080000034'::text AS serial)
SELECT (SELECT count(*) FROM public.filling_product_logs f, target t
        WHERE f.display_serial_no::text = t.serial)                    AS saved_rows,
       (SELECT count(*) FROM public.staging_product_logs e, target t
        WHERE e.serial_no = t.serial AND e.serial_label_code = 'display') AS own_link,
       (SELECT count(*) FROM public.staging_product_logs e, target t
        WHERE e.parent_serial_no = t.serial
          AND e.parent_serial_label_code = 'display')                  AS links_inside,
       (SELECT count(*) FROM public.staging_product_logs e, target t
        WHERE btrim(e.serial_no) = t.serial
           OR btrim(e.parent_serial_no) = t.serial)                    AS matches_when_trimmed;
