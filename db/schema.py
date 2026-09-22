import contextlib

from . import connection

# Keyed by (schema, table). This app has one staging table per session, so
# these hold at most a couple of entries -- a plain dict, not a TTL/LRU cache.
# Nothing in the app alters the staging table's schema mid-session, so there
# is no invalidation trigger; clear_cache() exists for tests only.
_columns_cache = {}
_pk_cache = {}


def clear_cache():
    _columns_cache.clear()
    _pk_cache.clear()


def get_columns(table, schema="public"):
    key = (schema, table)
    if key in _columns_cache:
        return _columns_cache[key]
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (schema, table),
            )
            result = [row[0] for row in cur.fetchall()]
    # An empty result is what _on_search reads as "table not found"
    # (main_window.py) -- caching it would turn one transient failure into a
    # false "not found" for the rest of the session, so only real schemas
    # (non-empty) are cached.
    if result:
        _columns_cache[key] = result
    return result


def get_primary_key_columns(table, schema="public"):
    key = (schema, table)
    if key in _pk_cache:
        return _pk_cache[key]
    with contextlib.closing(connection.get_connection()) as conn:
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
            result = [row[0] for row in cur.fetchall()]
    _pk_cache[key] = result
    return result
