from psycopg2 import sql

from .hierarchy import TRANSFER_COLUMN, TransferLockedError


# --- transfer lock -----------------------------------------------------------
#
# Rows whose is_transfer flag is true must not be updated or deleted. The flag is
# read off row dicts that the write paths already load with SELECT *, so a table
# that does not have the column simply has nothing locked.


def is_transferred(row):
    return bool(row.get(TRANSFER_COLUMN))


def split_transferred(originals, updates, deletes):
    """Drop the edits aimed at transferred rows.

    `originals` maps pk -> pre-edit row (see edge_mirror._fetch_rows_by_pk); an
    edit whose row is not in it is kept, as the writers already ignore those.
    Returns (updates, deletes, skipped) with `skipped` the pk tuples dropped.
    """
    def locked(pk_values):
        return is_transferred(originals.get(pk_values[0]) or {})

    kept_updates = [item for item in updates if not locked(item[0])]
    kept_deletes = [pk_values for pk_values in deletes if not locked(pk_values)]
    skipped = ([item[0] for item in updates if locked(item[0])]
               + [pk_values for pk_values in deletes if locked(pk_values)])
    return kept_updates, kept_deletes, skipped


def transferred_row_count(cur, schema, table, level, serial_no):
    """How many saved rows naming `serial_no` at `level` are already transferred."""
    cur.execute(
        sql.SQL("SELECT * FROM {schema}.{table} WHERE {col}::text = %s").format(
            schema=sql.Identifier(schema),
            table=sql.Identifier(table),
            col=sql.Identifier(f"{level}_serial_no"),
        ),
        (serial_no,),
    )
    names = [description[0] for description in cur.description]
    return sum(1 for values in cur.fetchall() if is_transferred(dict(zip(names, values))))


def refuse_transferred(cur, schema, table, level, serial_no, action):
    """Raise TransferLockedError if any row of this container is transferred."""
    locked = transferred_row_count(cur, schema, table, level, serial_no)
    if locked:
        raise TransferLockedError(
            f'Cannot {action} {level} "{serial_no}": {locked} of its row(s) are already '
            "transferred. Nothing was changed."
        )
