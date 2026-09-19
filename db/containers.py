import contextlib

from psycopg2 import sql

from . import connection
from .hierarchy import (LEVELS, CONTAINER_LEVELS, STAGING_EDGE_TABLE,
                        SerialConflictError)
from .serial_state import _set_serial_active


# --- whole-container rename --------------------------------------------------
#
# A container edge is found by serial + label code rather than by a row's
# <level>_source_id. Going through one row's edge id would only ever fix that
# row: a display is named by its own display->carton edge AND by the
# parent_serial_no of all ~6 unit->display edges beneath it, so a rename has to
# hit every edge naming the container at once or the two tables disagree.


def _container_edge_counts(cur, level, serial_no, schema):
    """(edges where the container is the child, edges where it is the parent)."""
    cur.execute(
        sql.SQL(
            "SELECT count(*) FILTER (WHERE serial_no = %s AND serial_label_code = %s), "
            "       count(*) FILTER (WHERE parent_serial_no = %s AND parent_serial_label_code = %s) "
            "FROM {schema}.{edges}"
        ).format(schema=sql.Identifier(schema), edges=sql.Identifier(STAGING_EDGE_TABLE)),
        (serial_no, level, serial_no, level),
    )
    return cur.fetchone()


def _serial_in_use(cur, level, serial_no, schema, table):
    """True if anything already answers to `serial_no`.

    Checked against every level in the edge table, not just `level`: a serial is
    meant to be unique across the whole label system, and nothing in the schema
    enforces that (see SerialConflictError).
    """
    cur.execute(
        sql.SQL(
            "SELECT 1 FROM {schema}.{edges} "
            "WHERE serial_no = %s OR parent_serial_no = %s LIMIT 1"
        ).format(schema=sql.Identifier(schema), edges=sql.Identifier(STAGING_EDGE_TABLE)),
        (serial_no, serial_no),
    )
    if cur.fetchone() is not None:
        return True
    cur.execute(
        sql.SQL("SELECT 1 FROM {schema}.{table} WHERE {col} = %s LIMIT 1").format(
            schema=sql.Identifier(schema),
            table=sql.Identifier(table),
            col=sql.Identifier(f"{level}_serial_no"),
        ),
        (serial_no,),
    )
    return cur.fetchone() is not None


def _apply_serial_rename(cur, level, old_serial, new_serial, schema, table):
    """Rewrite every mention of one serial at one level. Returns the row count.

    Works for `unit` too: a unit is a leaf, so the parent_serial_label_code =
    'unit' predicate simply matches nothing. The label-code predicate is what
    keeps a display rename from touching a unit that happens to share the string.
    """
    for serial_col, code_col in (
        ("serial_no", "serial_label_code"),
        ("parent_serial_no", "parent_serial_label_code"),
    ):
        cur.execute(
            sql.SQL(
                "UPDATE {schema}.{edges} SET {serial_col} = %s "
                "WHERE {serial_col} = %s AND {code_col} = %s"
            ).format(
                schema=sql.Identifier(schema),
                edges=sql.Identifier(STAGING_EDGE_TABLE),
                serial_col=sql.Identifier(serial_col),
                code_col=sql.Identifier(code_col),
            ),
            (new_serial, old_serial, level),
        )

    cur.execute(
        sql.SQL("UPDATE {schema}.{table} SET {col} = %s WHERE {col} = %s").format(
            schema=sql.Identifier(schema),
            table=sql.Identifier(table),
            col=sql.Identifier(f"{level}_serial_no"),
        ),
        (new_serial, old_serial),
    )
    return cur.rowcount


def container_serials(level, schema="public", limit=1000):
    """Every serial that names a container at `level`, for the picker."""
    if level not in CONTAINER_LEVELS:
        raise ValueError(f"{level} is not a container level")

    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "SELECT serial_no FROM ("
                    "  SELECT serial_no FROM {schema}.{edges} WHERE serial_label_code = %s"
                    "  UNION"
                    "  SELECT parent_serial_no FROM {schema}.{edges}"
                    "   WHERE parent_serial_label_code = %s"
                    ") s WHERE serial_no IS NOT NULL ORDER BY serial_no LIMIT %s"
                ).format(schema=sql.Identifier(schema), edges=sql.Identifier(STAGING_EDGE_TABLE)),
                (level, level, limit),
            )
            return [row[0] for row in cur.fetchall()]


def container_children(level, serial_no, schema="public"):
    """Direct children of one container, each with a count of its own children.

    The grandchild count is what tells the user how much sits under a child they
    are about to rename, so the second panel can show the weight of each row
    without a second round trip.
    """
    if level not in CONTAINER_LEVELS:
        raise ValueError(f"{level} is not a container level")

    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "SELECT ch.serial_no, ch.serial_label_code, count(g.id) "
                    "FROM {schema}.{edges} ch "
                    "LEFT JOIN {schema}.{edges} g "
                    "       ON g.parent_serial_no = ch.serial_no "
                    "      AND g.parent_serial_label_code = ch.serial_label_code "
                    "WHERE ch.parent_serial_no = %s AND ch.parent_serial_label_code = %s "
                    "GROUP BY ch.serial_no, ch.serial_label_code "
                    "ORDER BY ch.serial_no"
                ).format(schema=sql.Identifier(schema), edges=sql.Identifier(STAGING_EDGE_TABLE)),
                (serial_no, level),
            )
            return [
                {"serial_no": serial, "level": child_level, "children": grandkids}
                for serial, child_level, grandkids in cur.fetchall()
            ]


def rename_children(renames, schema="public", table="filling_product_logs"):
    """Rename several serials in one transaction — all of them, or none.

    `renames` is a sequence of (level, old_serial, new_serial). Used by the
    second panel, where the user has picked which children of a just-renamed
    container should follow it. Atomic because a half-applied batch would leave
    the operator guessing which rows still carry the old scheme.
    """
    renames = [tuple(r) for r in renames]
    if not renames:
        return {"renamed": 0, "rows": 0, "edges": 0}

    old_names = [old for _, old, _ in renames]
    new_names = [new for _, _, new in renames]

    for level, old, new in renames:
        if level not in LEVELS:
            raise ValueError(f"{level} is not a label level")
        if not new or not old or new == old:
            raise ValueError(f'"{old}" needs a different, non-empty new serial')
    if len(set(new_names)) != len(new_names):
        raise ValueError("Two children were given the same new serial")
    # A swap (A->B, B->A) is legal in the end state but not in any single
    # statement order, so it is refused rather than half-applied.
    collision = set(old_names) & set(new_names)
    if collision:
        raise ValueError(
            f"{', '.join(sorted(collision))} is both renamed and renamed onto. "
            "Apply this in two steps, via a temporary serial."
        )

    total_rows = 0
    total_edges = 0
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            for level, old, new in renames:
                as_child, as_parent = _container_edge_counts(cur, level, old, schema)
                if not (as_child or as_parent):
                    raise SerialConflictError(
                        f'No {level} named "{old}" exists in {STAGING_EDGE_TABLE}.'
                    )
                if _serial_in_use(cur, level, new, schema, table):
                    raise SerialConflictError(f'Serial "{new}" is already in use — pick another.')
                total_edges += as_child + as_parent

            for level, old, new in renames:
                total_rows += _apply_serial_rename(cur, level, old, new, schema, table)
                if level == "unit":
                    _set_serial_active(cur, schema, old, False)
                    _set_serial_active(cur, schema, new, True)

        conn.commit()

    return {"renamed": len(renames), "rows": total_rows, "edges": total_edges}


def container_rename_preview(level, serial_no, schema="public", table="filling_product_logs"):
    """Blast radius of renaming `serial_no`, so the user is told before agreeing."""
    if level not in CONTAINER_LEVELS:
        raise ValueError(f"{level} is not a container level")

    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            as_child, as_parent = _container_edge_counts(cur, level, serial_no, schema)
            cur.execute(
                sql.SQL("SELECT count(*) FROM {schema}.{table} WHERE {col} = %s").format(
                    schema=sql.Identifier(schema),
                    table=sql.Identifier(table),
                    col=sql.Identifier(f"{level}_serial_no"),
                ),
                (serial_no,),
            )
            rows = cur.fetchone()[0]
    return {"rows": rows, "edges": as_child + as_parent}


def rename_container(level, old_serial, new_serial, schema="public",
                     table="filling_product_logs"):
    """Rename one container everywhere it appears, in a single transaction.

    Raises SerialConflictError if the new serial is already in use. That check
    lives here rather than in the schema because staging_product_logs carries no
    unique constraint on the business key -- the database would otherwise let two
    containers share a name without complaint.
    """
    if level not in CONTAINER_LEVELS:
        raise ValueError(f"{level} is not a container level")
    if not new_serial or new_serial == old_serial:
        raise ValueError("The new serial must be a different, non-empty value")

    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            if _serial_in_use(cur, level, new_serial, schema, table):
                raise SerialConflictError(
                    f'Serial "{new_serial}" is already in use — pick another.'
                )

            as_child, as_parent = _container_edge_counts(cur, level, old_serial, schema)
            if not (as_child or as_parent):
                raise SerialConflictError(
                    f'No {level} named "{old_serial}" exists in {STAGING_EDGE_TABLE}.'
                )

            rows = _apply_serial_rename(cur, level, old_serial, new_serial, schema, table)

        conn.commit()

    return {"rows": rows, "edges": as_child + as_parent}
