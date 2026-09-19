import contextlib

from psycopg2 import sql

from . import connection


def fetch_distinct_values(table, column, conditions=None, limit=300, schema="public"):
    """Return ordered distinct values; limit=None uses PostgreSQL LIMIT NULL (all)."""
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
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [row[0] for row in cur.fetchall()]


def container_groups(table, columns, conditions=(), schema="public", product_column="product_name"):
    """Aggregate complete packaging paths, independently of the record-grid limit."""
    names = [f"{level}_serial_no" for level in ("carton", "inner", "display", "unit")]
    present = [name for name in names if name in columns]
    if not present:
        return []
    fields = sql.SQL(", ").join(
        sql.Identifier(name) if name in columns else sql.SQL("NULL") for name in names
    )
    where = sql.SQL(" AND ").join(cond for cond, _ in conditions) if conditions else sql.SQL("TRUE")
    products = (
        sql.SQL("ARRAY_AGG(DISTINCT {0}::text) FILTER (WHERE {0} IS NOT NULL)").format(sql.Identifier(product_column))
        if product_column in columns else sql.SQL("ARRAY[]::text[]")
    )
    query = sql.SQL(
        "SELECT {fields}, COUNT(*), {products} FROM {schema}.{table} WHERE {where} GROUP BY {groups}"
    ).format(fields=fields, schema=sql.Identifier(schema), table=sql.Identifier(table),
             where=where, products=products, groups=sql.SQL(", ").join(map(sql.Identifier, present)))
    params = [p for _, values in conditions for p in values]
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


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

    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            col_names = [d.name for d in cur.description]
    return col_names, rows


def _save_changes(cur, table, pk_columns, updates, deletes, schema):
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


def save_changes(table, pk_columns, updates, deletes, schema="public"):
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            _save_changes(cur, table, pk_columns, updates, deletes, schema)

        conn.commit()
