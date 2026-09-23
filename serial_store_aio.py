import asyncio
import contextlib
import logging
from pathlib import Path

from dotenv import load_dotenv

# When run by the Windows Service Control Manager (or as a frozen exe), the
# working directory is unpredictable, so never rely on cwd. Resolving against
# __file__ covers both cases: the source tree when running from source, and the
# _MEIPASS extraction dir when frozen -- where .env is bundled by DataRework.spec
# so the deployed dist/ folder carries no plaintext credentials.
load_dotenv(Path(__file__).resolve().parent / ".env")

from psycopg2 import sql
from psycopg2.extras import execute_values

from db import get_connection

logger = logging.getLogger(__name__)


def _fetch_counts(schema="public"):
    """Count active and damaged serials in staging_serial_data, per roll_no.

    One query for both: they read the same rows, so there is no reason to scan
    the table twice for two independent totals. Returns
    {roll_no: (used_count, damaged_count)}.
    """
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            query = sql.SQL(
                "SELECT roll_no, COUNT(*) FILTER (WHERE activate) AS used_count, "
                "COUNT(*) FILTER (WHERE is_damaged) AS damaged_count "
                "FROM {schema}.staging_serial_data "
                "WHERE roll_no IS NOT NULL "
                "GROUP BY roll_no"
            ).format(schema=sql.Identifier(schema))
            cur.execute(query)
            return {roll_no: (used, damaged) for roll_no, used, damaged in cur.fetchall()}


def _apply_counts(counts, schema="public"):
    """Write the roll_no -> (used, damaged) counts into serial_store.

    Roll numbers present in `counts` get their exact counts; every other
    roll_no in serial_store is reset to 0 on both columns so neither goes
    stale (e.g. a roll_no whose only serials were all deleted).
    """
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            if counts:
                update_sql = sql.SQL(
                    "UPDATE {schema}.serial_store AS s "
                    "SET used_serials = v.used, damaged_serials = v.damaged "
                    "FROM (VALUES %s) AS v (roll_no, used, damaged) "
                    "WHERE s.roll_no = v.roll_no"
                ).format(schema=sql.Identifier(schema))
                execute_values(
                    cur, update_sql.as_string(cur),
                    [(roll_no, used, damaged) for roll_no, (used, damaged) in counts.items()],
                )

                reset_sql = sql.SQL(
                    "UPDATE {schema}.serial_store "
                    "SET used_serials = 0, damaged_serials = 0 "
                    "WHERE roll_no NOT IN %s"
                ).format(schema=sql.Identifier(schema))
                cur.execute(reset_sql, (tuple(counts.keys()),))
            else:
                reset_sql = sql.SQL(
                    "UPDATE {schema}.serial_store SET used_serials = 0, damaged_serials = 0"
                ).format(schema=sql.Identifier(schema))
                cur.execute(reset_sql)

            conn.commit()


async def sync_serial_counts_once(schema="public"):
    """Recompute and apply used_serials and damaged_serials for every roll_no,
    in the same pass. Returns {roll_no: (used_count, damaged_count)}."""
    counts = await asyncio.to_thread(_fetch_counts, schema)
    await asyncio.to_thread(_apply_counts, counts, schema)
    #logger.info("Synced used/damaged serials for %d roll_no(s): %s", len(counts), counts)
    return counts


async def run_forever(interval: float = 10.0, schema="public"):
    while True:
        try:
            await sync_serial_counts_once(schema)
        except Exception:
            logger.exception("serial counts sync cycle failed")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
