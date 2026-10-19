import contextlib
import datetime

from psycopg2 import sql

from . import connection
from .hierarchy import (SERIAL_DATA_TABLE, SerialInventoryError, SerialInUseError,
                        SerialUnavailableError)


# Activating a serial leaves alone a row that is already damaged or already in
# use. Text comparison because it also holds if is_use is not a boolean column.
_NOT_DAMAGED_OR_IN_USE = sql.SQL(
    " AND COALESCE(is_damaged::text, '') <> 'true'"
    " AND COALESCE(is_use::text, '') <> 'true'"
)


def _set_serial_active(cur, schema, serial_no, active, tag_name=None, required=False):
    is_use = "rework" if active else None
    tag_name = tag_name if active else None
    time = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=7))
        ) if active else None

    if not serial_no:
        return 0
    cur.execute(
        sql.SQL(
            "UPDATE {schema}.{tbl} SET activate = %s, is_use = %s, "
            "activate_by = %s , "
            "activate_at = %s "
            "WHERE btrim(serial_no) = btrim(%s)"
        ).format(
            schema=sql.Identifier(schema),
            tbl=sql.Identifier(SERIAL_DATA_TABLE),
        ) + (_NOT_DAMAGED_OR_IN_USE if active else sql.SQL("")),
        (active, is_use, tag_name, time, serial_no),
    )
    updated = cur.rowcount
    if required and updated != 1:
        if updated == 0 and active:
            _refuse_unavailable(cur, schema, serial_no)
        raise SerialInventoryError(
            f'Serial "{serial_no}" matches {updated} row(s) in '
            f"{SERIAL_DATA_TABLE}; expected exactly 1. "
            "Usage totals would be wrong, so nothing was changed."
        )
    return updated


def _refuse_unavailable(cur, schema, serial_no):
    """Raise SerialUnavailableError if the one row for `serial_no` is damaged or
    in use; return quietly (so the caller reports a missing/duplicate row) if not."""
    cur.execute(
        sql.SQL(
            "SELECT COALESCE(is_damaged::text, ''), COALESCE(is_use::text, '') "
            "FROM {schema}.{tbl} WHERE btrim(serial_no) = btrim(%s) LIMIT 2"
        ).format(
            schema=sql.Identifier(schema),
            tbl=sql.Identifier(SERIAL_DATA_TABLE),
        ),
        (serial_no,),
    )
    rows = cur.fetchall()
    if len(rows) != 1:
        return
    damaged, in_use = rows[0]
    if damaged == "true":
        raise SerialUnavailableError(
            f'Serial "{serial_no}" is damaged and cannot be used. '
            "Nothing was changed."
        )
    if in_use == "true":
        raise SerialUnavailableError(
            f'Serial "{serial_no}" is already in use. Nothing was changed.'
        )


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
