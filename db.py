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

def update_staging_serial(updates, deletes, schema="public", table = "staging_serial_data"):
    if deletes:
        del_ids = tuple(x[0] for x in deletes)
        set_staging_serial(del_ids, schema, table, '')

    if not updates:
        return

    # Keep only rows where 'unit_serial_no' itself changed, mapping id -> new serial
    serial_changes = {
        item_id[0]: data['unit_serial_no']
        for item_id, data in updates
        if 'unit_serial_no' in data
    }

    if not serial_changes:
        return

    item_ids = tuple(serial_changes.keys())
    new_serials = tuple(serial_changes.values())
    set_staging_serial(item_ids, schema, table, 'update', new_serials=new_serials)


def set_staging_serial(id_list, schema, table, mode: str, new_serials=None):
    if not id_list:
        return

    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            old_serial_sql = sql.SQL(
                "SELECT unit_serial_no FROM {schema}.filling_product_logs WHERE id IN %s"
            ).format(schema=sql.Identifier(schema))
            cur.execute(old_serial_sql, (tuple(id_list),))
            old_serials = tuple(row[0] for row in cur.fetchall() if row[0] is not None)

            if old_serials:
                set_false_sql = sql.SQL(
                    "UPDATE {schema}.{table} SET activate = False WHERE serial_no IN %s"
                ).format(schema=sql.Identifier(schema), table=sql.Identifier(table))
                cur.execute(set_false_sql, (old_serials,))

            if mode == 'update' and new_serials:
                set_true_sql = sql.SQL(
                    "UPDATE {schema}.{table} SET activate = True WHERE serial_no IN %s"
                ).format(schema=sql.Identifier(schema), table=sql.Identifier(table))
                cur.execute(set_true_sql, (tuple(new_serials),))

            conn.commit()
