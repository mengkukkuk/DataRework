from psycopg2 import sql

from .hierarchy import SERIAL_DATA_TABLE, SerialInventoryError


def _set_serial_active(cur, schema, serial_no, active, tag_name=None, required=False):
    """Flip one unit serial's activate flag; the serial_store sync picks this up.

    Matched on the *trimmed* serial: staging_serial_data stores a trailing space
    ('260800000001 ') while the logs and edge table store it clean, and varchar
    comparison is not blank-padded.

    `required=True` refuses the write when the serial has no inventory row,
    since used_serials is derived by counting those rows -- activating a serial
    that is not in the pool would undercount it silently. Deactivations pass
    required=False: a serial already absent is already not counted.

    Returns the number of inventory rows updated.
    """
    if not serial_no:
        return 0
    cur.execute(
        sql.SQL(
            "UPDATE {schema}.{tbl} SET activate = %s, "
            "activate_by = COALESCE(%s, activate_by) "
            "WHERE btrim(serial_no) = btrim(%s)"
        ).format(
            schema=sql.Identifier(schema),
            tbl=sql.Identifier(SERIAL_DATA_TABLE),
        ),
        (active, tag_name, serial_no),
    )
    if required and cur.rowcount != 1:
        raise SerialInventoryError(
            f'Serial "{serial_no}" matches {cur.rowcount} row(s) in '
            f"{SERIAL_DATA_TABLE}; expected exactly 1. "
            "Usage totals would be wrong, so nothing was changed."
        )
    return cur.rowcount


def _set_serials_inactive(cur, schema, serial_nos, tag_name=None):
    """Deactivate many unit serials in one statement.

    Same trimmed match and same `activate_by` rule as _set_serial_active, but one
    pass over staging_serial_data instead of one per serial: the trimmed match is
    not index-friendly, so a carton of ~130 units would otherwise cost ~130 scans.
    A serial with no inventory row is simply not counted, as with a single
    deactivation. Returns the number of inventory rows updated.
    """
    wanted = sorted({str(serial).strip() for serial in serial_nos
                     if serial is not None and str(serial).strip()})
    if not wanted:
        return 0
    cur.execute(
        sql.SQL(
            "UPDATE {schema}.{tbl} SET activate = false, "
            "activate_by = COALESCE(%s, activate_by) "
            "WHERE btrim(serial_no) = ANY(%s)"
        ).format(
            schema=sql.Identifier(schema),
            tbl=sql.Identifier(SERIAL_DATA_TABLE),
        ),
        (tag_name, wanted),
    )
    return cur.rowcount
