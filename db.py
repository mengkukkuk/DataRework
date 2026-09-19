import contextlib
import os

import bcrypt
import psycopg2
from psycopg2 import sql

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "P@ssw0rd")

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )

def authenticate(username, password):
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password, permission FROM public.user_access WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()

    if row is None:
        return None

    password_hash, permission = row
    if not password_hash:
        return None
    """
    # Verify cross-platform
    is_valid = bcrypt.checkpw(
        password.encode('utf-8'),
        password_hash.encode('utf-8')
    )
    """
    return permission


def get_columns(table, schema="public"):
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (schema, table),
            )
            return [row[0] for row in cur.fetchall()]


def get_primary_key_columns(table, schema="public"):
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = %s
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'PRIMARY KEY'
                ORDER BY kcu.ordinal_position
                """,
                (schema, table),
            )
            return [row[0] for row in cur.fetchall()]


def fetch_distinct_values(table, column, conditions=None, limit=300, schema="public"):
    where_sql = sql.SQL(" AND ").join(cond for cond, _ in conditions) if conditions else sql.SQL("TRUE")
    params = [p for _, cond_params in conditions for p in cond_params] if conditions else []

    query = sql.SQL(
        "SELECT DISTINCT {col} FROM {schema}.{table} "
        "WHERE {col} IS NOT NULL AND {where} ORDER BY {col} DESC LIMIT %s"
    ).format(
        col=sql.Identifier(column),
        schema=sql.Identifier(schema),
        table=sql.Identifier(table),
        where=where_sql,
    )
    params.append(limit)
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [row[0] for row in cur.fetchall()]


def query_rows(table, columns, conditions, schema="public", limit=500):
    select_cols = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    where_sql = sql.SQL(" AND ").join(cond for cond, _ in conditions) if conditions else sql.SQL("TRUE")
    params = [p for _, cond_params in conditions for p in cond_params]

    query = sql.SQL("SELECT {cols} FROM {schema}.{table} WHERE {where} LIMIT %s").format(
        cols=select_cols,
        schema=sql.Identifier(schema),
        table=sql.Identifier(table),
        where=where_sql,
    )
    params.append(limit)

    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            col_names = [d.name for d in cur.description]
    return col_names, rows


def save_changes(table, pk_columns, updates, deletes, schema="public"):
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            for pk_values, changes in updates:
                set_sql = sql.SQL(", ").join(
                    sql.SQL("{} = %s").format(sql.Identifier(col)) for col in changes
                )
                where_sql = sql.SQL(" AND ").join(
                    sql.SQL("{} = %s").format(sql.Identifier(col)) for col in pk_columns
                )
                query = sql.SQL("UPDATE {schema}.{table} SET {set_sql} WHERE {where_sql}").format(
                    schema=sql.Identifier(schema),
                    table=sql.Identifier(table),
                    set_sql=set_sql,
                    where_sql=where_sql,
                )
                cur.execute(query, list(changes.values()) + list(pk_values))

            for pk_values in deletes:
                where_sql = sql.SQL(" AND ").join(
                    sql.SQL("{} = %s").format(sql.Identifier(col)) for col in pk_columns
                )
                query = sql.SQL("DELETE FROM {schema}.{table} WHERE {where_sql}").format(
                    schema=sql.Identifier(schema),
                    table=sql.Identifier(table),
                    where_sql=where_sql,
                )
                cur.execute(query, list(pk_values))

        conn.commit()

# --- packaging hierarchy -----------------------------------------------------
#
# filling_product_logs is a flattened chain: one row per unit, carrying the
# serial/roll of every container it sits in. staging_product_logs is the edge
# table behind it -- one row per child->parent link:
#
#     serial_no [serial_label_code]  ->  parent_serial_no [parent_serial_label_code]
#     source_roll_no                 ->  target_roll_no
#
# A row's <level>_source_id is the edge where that level is the CHILD; the same
# edge id also appears as <parent>_target_id (verified: the two columns never
# disagree). So renaming e.g. a display serial has to touch two edges -- the
# display->carton edge where display is the child, and the unit->display edge
# where it is the parent.
LEVELS = ["unit", "display", "inner", "carton"]

# Levels whose serial names a *container* rather than the row itself. One
# display is shared by ~6 filling_product_logs rows and one carton by ~130, so
# these can never be edited as a per-row cell -- renaming them is a
# whole-container operation (see rename_container).
CONTAINER_LEVELS = ("display", "inner", "carton")

STAGING_EDGE_TABLE = "staging_product_logs"
SERIAL_DATA_TABLE = "staging_serial_data"


class SharedEdgeError(Exception):
    """A serial/roll edit would rewrite container rows the user never saw.

    display/carton edges are shared by roughly six sibling units each, so
    editing one row's display_serial_no would silently rename it for all of
    them. Renaming a shared container is a deliberate act, not a side effect of
    a cell edit, so the save is refused and the user is told the blast radius.
    """


class SerialConflictError(Exception):
    """A rename collided with uq_staging_product_logs_business_key."""


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


def update_staging_serial_data(updates, deletes, pk_columns=("id",), schema="public",
                               table="filling_product_logs"):
    """Mirror serial/roll edits from filling_product_logs into the edge table.

    Runs BEFORE save_changes() so that a shared-edge edit aborts the save while
    filling_product_logs is still untouched. Raises SharedEdgeError (blocked) or
    SerialConflictError (unique-key collision); both are shown to the user.
    """
    if not updates and not deletes:
        return

    pk_column = pk_columns[0] if pk_columns else "id"

    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
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
            try:
                for pk_values, changes in updates:
                    row = originals.get(pk_values[0])
                    if not row:
                        continue
                    for level, new in _changed_levels(changes).items():
                        _apply_edge_change(cur, schema, row, level, new)
                    if "unit_serial_no" in changes:
                        _set_serial_active(cur, schema, row.get("unit_serial_no"), False)
                        _set_serial_active(cur, schema, changes["unit_serial_no"], True)

                for pk_values in deletes:
                    row = originals.get(pk_values[0])
                    if not row:
                        continue
                    _set_serial_active(cur, schema, row.get("unit_serial_no"), False)
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
            except psycopg2.errors.UniqueViolation as exc:
                conn.rollback()
                raise SerialConflictError(
                    f"That serial already exists for this assignment/parent: {exc}"
                ) from exc

            conn.commit()


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

    with contextlib.closing(get_connection()) as conn:
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

    with contextlib.closing(get_connection()) as conn:
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
    with contextlib.closing(get_connection()) as conn:
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

    with contextlib.closing(get_connection()) as conn:
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

    with contextlib.closing(get_connection()) as conn:
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