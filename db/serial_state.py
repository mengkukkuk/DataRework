import contextlib

from psycopg2 import sql

from . import connection
from .hierarchy import SERIAL_DATA_TABLE, SerialInventoryError, SerialInUseError


def _set_serial_active(cur, schema, serial_no, active, tag_name=None, required=False):
    """Flip one serial's activate flag (unit or container -- level is not part
    of the match); the serial_store sync picks this up.

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


def report_damage(serial_no, schema="public"):
    """Flag one serial as damaged in staging_serial_data. Any level -- the
    match is on serial_no alone, same as everywhere else in this module.

    Refuses while the serial is still active: SerialInventoryError if it has
    no inventory row at all, SerialInUseError if it does but activate=true.
    Checked and applied in the same transaction; the write repeats the
    activate=false condition so a serial that went active again between the
    read and the write can't slip through, in which case it also raises
    SerialInUseError rather than reporting a false success. Matched on the
    *trimmed* serial, same convention as every other lookup against this
    table. Returns {"serial_no": ..., "roll_no": ...} on success.
    """
    if not serial_no or not str(serial_no).strip():
        raise ValueError("Type a serial number to report.")
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "SELECT roll_no, activate FROM {schema}.{tbl} "
                    "WHERE btrim(serial_no) = btrim(%s) LIMIT 1"
                ).format(schema=sql.Identifier(schema), tbl=sql.Identifier(SERIAL_DATA_TABLE)),
                (serial_no,),
            )
            row = cur.fetchone()
            if row is None:
                raise SerialInventoryError(
                    f'No serial "{serial_no}" found in {SERIAL_DATA_TABLE}.'
                )
            roll_no, active = row
            if active:
                raise SerialInUseError(
                    f'Serial "{serial_no}" is still active -- take it out of use '
                    "before reporting it damaged."
                )

            cur.execute(
                sql.SQL(
                    "UPDATE {schema}.{tbl} SET is_damaged = true "
                    "WHERE btrim(serial_no) = btrim(%s) AND activate = false"
                ).format(schema=sql.Identifier(schema), tbl=sql.Identifier(SERIAL_DATA_TABLE)),
                (serial_no,),
            )
            if cur.rowcount != 1:
                raise SerialInUseError(
                    f'Serial "{serial_no}" went active again before the report was '
                    "saved. Nothing was changed -- try again."
                )

        conn.commit()
    return {"serial_no": serial_no, "roll_no": roll_no}
