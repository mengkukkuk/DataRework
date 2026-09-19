import asyncio
import contextlib
import logging

from dotenv import load_dotenv
load_dotenv()

from psycopg2 import sql
from psycopg2.extras import execute_values

from db import get_connection

logger = logging.getLogger(__name__)


def _fetch_active_counts(schema="public"):
    """Count active (activate = true) serials in staging_serial_data, per roll_no."""
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            query = sql.SQL(
                "SELECT roll_no, COUNT(*) FILTER (WHERE activate) AS used_count "
                "FROM {schema}.staging_serial_data "
                "WHERE roll_no IS NOT NULL "
                "GROUP BY roll_no"
            ).format(schema=sql.Identifier(schema))
            cur.execute(query)
            return {roll_no: count for roll_no, count in cur.fetchall()}


def _apply_used_serials(counts, schema="public"):
    """Write the roll_no -> used-serial counts into serial_store.

    Roll numbers present in `counts` get their exact count; every other
    roll_no in serial_store is reset to 0 so the column never goes stale.
    """
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            if counts:
                update_sql = sql.SQL(
                    "UPDATE {schema}.serial_store AS s "
                    "SET used_serials = v.cnt "
                    "FROM (VALUES %s) AS v (roll_no, cnt) "
                    "WHERE s.roll_no = v.roll_no"
                ).format(schema=sql.Identifier(schema))
                execute_values(cur, update_sql.as_string(cur), list(counts.items()))

                reset_sql = sql.SQL(
                    "UPDATE {schema}.serial_store "
                    "SET used_serials = 0 "
                    "WHERE roll_no NOT IN %s"
                ).format(schema=sql.Identifier(schema))
                cur.execute(reset_sql, (tuple(counts.keys()),))
            else:
                reset_sql = sql.SQL(
                    "UPDATE {schema}.serial_store SET used_serials = 0"
                ).format(schema=sql.Identifier(schema))
                cur.execute(reset_sql)

            conn.commit()


async def sync_used_serials_once(schema="public"):
    """Recompute and apply used_serials for every roll_no. Returns the counts."""
    counts = await asyncio.to_thread(_fetch_active_counts, schema)
    await asyncio.to_thread(_apply_used_serials, counts, schema)
    logger.info("Synced used_serials for %d roll_no(s): %s", len(counts), counts)
    return counts


async def run_forever(interval: float = 10.0, schema="public"):
    while True:
        try:
            await sync_used_serials_once(schema)
        except Exception:
            logger.exception("used_serials sync cycle failed")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
