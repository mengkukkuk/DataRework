from psycopg2 import sql

from .hierarchy import SERIAL_DATA_TABLE


def _set_serial_active(cur, schema, serial_no, active, tag_name=None):
    """Flip one unit serial's activate flag; the serial_store sync picks this up.

    Matched on the *trimmed* serial. staging_serial_data stores serials with a
    trailing space ('260800000001 ') while filling_product_logs and the edge
    table store them clean ('260800000001'). varchar comparison is not
    blank-padded, so a plain `serial_no = %s` matched nothing: a rename updated
    the logs correctly and left the serial inventory untouched.

    activate_by is coalesced so callers that do not know the operator (the
    rename paths) can flip the flag without erasing who activated the serial.

    Returns the number of inventory rows updated. 0 means the serial is not in
    the pool, and used_serials will be wrong until it is.
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
    return cur.rowcount
