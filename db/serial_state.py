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


def _roll_no_for_serial(cur, schema, serial_no):
    """The roll_no staging_serial_data has on file for `serial_no`, or None"""
    if not serial_no:
        return None
    cur.execute(
        sql.SQL(
            "SELECT roll_no FROM {schema}.{tbl} WHERE btrim(serial_no) = btrim(%s) LIMIT 1"
        ).format(
            schema=sql.Identifier(schema),
            tbl=sql.Identifier(SERIAL_DATA_TABLE),
        ),
        (serial_no,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _set_serials_inactive(cur, schema, serial_nos, tag_name=None):
    """ Deactivate many serials in one statement (unit or container -- level is not
    part of the match) """
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
