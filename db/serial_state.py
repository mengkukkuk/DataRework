from psycopg2 import sql

from .hierarchy import SERIAL_DATA_TABLE


def _set_serial_active(cur, schema, serial_no, active):
    """Flip one unit serial's activate flag; the serial_store sync picks this up."""
    if not serial_no:
        return
    cur.execute(
        sql.SQL("UPDATE {schema}.{tbl} SET activate = %s WHERE serial_no = %s").format(
            schema=sql.Identifier(schema),
            tbl=sql.Identifier(SERIAL_DATA_TABLE),
        ),
        (active, serial_no),
    )
