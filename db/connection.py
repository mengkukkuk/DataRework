import os
import threading

import psycopg2
from psycopg2 import pool

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "P@ssw0rd")

# Remote-link resilience: fail a hung connection attempt fast, and let TCP
# notice a dead peer instead of hanging on a socket nobody is answering.
DB_CONNECT_TIMEOUT = int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))
DB_KEEPALIVES_IDLE = int(os.environ.get("DB_KEEPALIVES_IDLE", "30"))
DB_KEEPALIVES_INTERVAL = int(os.environ.get("DB_KEEPALIVES_INTERVAL", "10"))
DB_KEEPALIVES_COUNT = int(os.environ.get("DB_KEEPALIVES_COUNT", "3"))
DB_SSLMODE = os.environ.get("DB_SSLMODE", "prefer")

# Small: this is a single UI thread plus at most one background worker thread
# (db_worker.py) sharing the pool, not a server handling concurrent clients.
DB_POOL_MIN = int(os.environ.get("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.environ.get("DB_POOL_MAX", "3"))

_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    """The process-wide connection pool, built on first use.

    Not built at import time: an eager pool would open a real socket during
    `import db`, which would turn a startup DB outage into an import crash
    instead of the caught OperationalError callers already handle, and would
    reach past tests/test_db_package.py's patch of psycopg2.connect (applied
    after `import db`, since the module must be importable to patch it).
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pool.ThreadedConnectionPool(
                    DB_POOL_MIN, DB_POOL_MAX,
                    host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
                    connect_timeout=DB_CONNECT_TIMEOUT,
                    keepalives=1,
                    keepalives_idle=DB_KEEPALIVES_IDLE,
                    keepalives_interval=DB_KEEPALIVES_INTERVAL,
                    keepalives_count=DB_KEEPALIVES_COUNT,
                    application_name="DataRework",
                    sslmode=DB_SSLMODE,
                )
    return _pool


class _PooledConnection:
    """A pooled connection that returns itself to the pool on close() instead
    of being destroyed.

    psycopg2's connection is a C-extension type, so its `close` can't be
    rebound per-instance -- this proxy stands in for it. Every existing call
    site does `with contextlib.closing(get_connection()) as conn:`, which only
    ever calls `.close()`, so nothing else has to change.
    """

    def __init__(self, pool_, conn):
        self._pool = pool_
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        self._pool.putconn(self._conn)


def get_connection():
    """One connection, checked out from the process pool.

    Not validated on checkout: a connection that went stale while idle in the
    pool (a network blip, a firewall's idle timeout) is only discoverable by
    using it, and pre-checking every checkout with a round trip would
    reintroduce the per-call latency pooling exists to avoid. A caller that
    hits this raises OperationalError exactly as it would without a pool
    (every call site already handles it); the pool's own putconn() then
    evicts that connection rather than pooling it back (see _PooledConnection
    .close()), so the next attempt gets a healthy one instead of the same
    stale one again.
    """
    connection_pool = _get_pool()
    return _PooledConnection(connection_pool, connection_pool.getconn())
