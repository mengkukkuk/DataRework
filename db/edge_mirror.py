import contextlib

import psycopg2
from psycopg2 import sql

from . import connection
from . import queries
from .hierarchy import (LEVELS, STAGING_EDGE_TABLE,
                        SharedEdgeError, SerialConflictError)
from .serial_state import _set_serial_active


def _edge_id_column(level):
    """The filling_product_logs column holding the edge where `level` is the child."""
    return f"{level}_source_id"


def _changed_levels(changes):
    """Map {level: {'serial': new, 'roll': new}} for the serial/roll edits in `changes`."""
    touched = {}
    for level in LEVELS:
        if f"{level}_serial_no" in changes:
            touched.setdefault(level, {})["serial"] = changes[f"{level}_serial_no"]
        if f"{level}_roll_no" in changes:
            touched.setdefault(level, {})["roll"] = changes[f"{level}_roll_no"]
    return touched


def _fetch_rows_by_pk(cur, schema, table, pk_column, pk_values_list):
    """Load the pre-edit filling_product_logs rows for the ids being saved."""
    if not pk_values_list:
        return {}
    cur.execute(
        sql.SQL("SELECT * FROM {schema}.{table} WHERE {pk} = ANY(%s)").format(
            schema=sql.Identifier(schema),
            table=sql.Identifier(table),
            pk=sql.Identifier(pk_column),
        ),
        ([v[0] for v in pk_values_list],),
    )
    cols = [d[0] for d in cur.description]
    return {row[cols.index(pk_column)]: dict(zip(cols, row)) for row in cur.fetchall()}


def _count_edge_siblings(cur, schema, table, edge_column, edge_id, own_pk, pk_column):
    """How many OTHER rows hang off the same edge (i.e. would be collaterally renamed)."""
    cur.execute(
        sql.SQL(
            "SELECT COUNT(*) FROM {schema}.{table} "
            "WHERE {edge_col} = %s AND {pk} <> %s"
        ).format(
            schema=sql.Identifier(schema),
            table=sql.Identifier(table),
            edge_col=sql.Identifier(edge_column),
            pk=sql.Identifier(pk_column),
        ),
        (edge_id, own_pk),
    )
    return cur.fetchone()[0]


def _apply_edge_change(cur, schema, row, level, new):
    """Write one level's new serial/roll onto both edges it takes part in."""
    child_edge = row.get(_edge_id_column(level))
    # The edge where this level is the PARENT is the child edge of the level below.
    idx = LEVELS.index(level)
    parent_edge = row.get(_edge_id_column(LEVELS[idx - 1])) if idx > 0 else None

    for edge_id, serial_col, roll_col in (
        (child_edge, "serial_no", "source_roll_no"),
        (parent_edge, "parent_serial_no", "target_roll_no"),
    ):
        if edge_id is None:
            continue
        assignments, params = [], []
        if "serial" in new:
            assignments.append(sql.SQL("{} = %s").format(sql.Identifier(serial_col)))
            params.append(new["serial"])
        if "roll" in new:
            assignments.append(sql.SQL("{} = %s").format(sql.Identifier(roll_col)))
            params.append(new["roll"])
        if not assignments:
            continue
        cur.execute(
            sql.SQL("UPDATE {schema}.{edges} SET {sets} WHERE id = %s").format(
                schema=sql.Identifier(schema),
                edges=sql.Identifier(STAGING_EDGE_TABLE),
                sets=sql.SQL(", ").join(assignments),
            ),
            params + [edge_id],
        )


def _update_staging_serial_data(cur, updates, deletes, pk_columns, schema, table,tag_name):
    pk_column = pk_columns[0] if pk_columns else "id"

    originals = _fetch_rows_by_pk(
        cur, schema, table, pk_column,
        [pk for pk, _ in updates] + list(deletes),
    )

    # Pass 1: refuse the whole save if any edit lands on a shared edge.
    blocked = []
    for pk_values, changes in updates:
        row = originals.get(pk_values[0])
        if not row:
            continue
        for level in _changed_levels(changes):
            edge_id = row.get(_edge_id_column(level))
            if edge_id is None:
                continue
            shared = _count_edge_siblings(
                cur, schema, table, _edge_id_column(level),
                edge_id, pk_values[0], pk_column,
            )
            if shared:
                blocked.append(
                    f'{level}_serial_no "{row.get(f"{level}_serial_no")}" '
                    f"is shared with {shared} other row(s)"
                )
    if blocked:
        raise SharedEdgeError(
            "Cannot save: " + "; ".join(blocked)
            + ". Editing a shared container would rename it for those rows too."
        )

    # Pass 2: apply. Keyed on edge id, never on serial text, so a rename
    # cannot mismatch rows the way the old positional zip could.
    for pk_values, changes in updates:
        row = originals.get(pk_values[0])
        if not row:
            continue
        for level, new in _changed_levels(changes).items():
            _apply_edge_change(cur, schema, row, level, new)
        if "unit_serial_no" in changes:
            _set_serial_active(cur, schema, row.get("unit_serial_no"), False, tag_name)
            _set_serial_active(cur, schema, changes["unit_serial_no"], True, tag_name,
                               required=True)

    for pk_values in deletes:
        row = originals.get(pk_values[0])
        if not row:
            continue
        _set_serial_active(cur, schema, row.get("unit_serial_no"), False,tag_name)
        # Only the unit edge is private to this row; display/carton
        # edges stay, since sibling rows still reference them.
        edge_id = row.get(_edge_id_column("unit"))
        if edge_id is not None:
            cur.execute(
                sql.SQL("DELETE FROM {schema}.{edges} WHERE id = %s").format(
                    schema=sql.Identifier(schema),
                    edges=sql.Identifier(STAGING_EDGE_TABLE),
                ),
                (edge_id,),
            )


def update_staging_serial_data(updates, deletes, pk_columns=("id",), schema="public",
                               table="filling_product_logs"):
    """Mirror serial/roll edits from filling_product_logs into the edge table.

    Runs BEFORE save_changes() so that a shared-edge edit aborts the save while
    filling_product_logs is still untouched. Raises SharedEdgeError (blocked) or
    SerialConflictError (unique-key collision); both are shown to the user.
    """
    if not updates and not deletes:
        return

    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            try:
                _update_staging_serial_data(cur, updates, deletes, pk_columns, schema, table, tag_name=None)
            except psycopg2.errors.UniqueViolation as exc:
                conn.rollback()
                raise SerialConflictError(
                    f"That serial already exists for this assignment/parent: {exc}"
                ) from exc

        conn.commit()


def save_grid_changes(table, pk_columns, updates, deletes, schema="public",tag_name=None):
    """Atomically mirror edge data and write the grid edit in one transaction.

    The mirror phase runs first on purpose: _update_staging_serial_data completes
    its entire shared-edge validation pass and raises SharedEdgeError *before* it
    touches any row.  Placing it first therefore guarantees that a shared-container
    edit aborts the whole save before filling_product_logs is modified at all —
    the same safety invariant as the old two-call sequence, but now the two phases
    share one connection and one commit, so a failure in the grid phase also rolls
    back the mirror writes rather than leaving the edge table and filling table
    inconsistent.

    Returns None immediately when both `updates` and `deletes` are empty, without
    opening a connection.

    UniqueViolation from either phase or the commit is translated into
    SerialConflictError (same message the standalone update_staging_serial_data
    uses) so the caller does not need to know which phase collided.

    Every other exception — including SharedEdgeError and psycopg2.OperationalError
    — rolls back and propagates unchanged, so the existing except clauses in
    main_window._on_save keep working without modification.

    Rollback failures are suppressed via contextlib.suppress so a dead connection
    cannot mask the original exception.
    """
    if not updates and not deletes:
        return None

    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            try:
                _update_staging_serial_data(cur, updates, deletes, pk_columns, schema, table, tag_name)
                queries._save_changes(cur, table, pk_columns, updates, deletes, schema)
                conn.commit()
            except psycopg2.errors.UniqueViolation as exc:
                with contextlib.suppress(Exception):
                    conn.rollback()
                raise SerialConflictError(
                    f"That serial already exists for this assignment/parent: {exc}"
                ) from exc
            except Exception:
                with contextlib.suppress(Exception):
                    conn.rollback()
                raise
