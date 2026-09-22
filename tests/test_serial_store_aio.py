"""serial_store_aio.py: syncing used_serials and damaged_serials into
serial_store from staging_serial_data, per roll_no, in one pass.

serial_store_aio imports `get_connection` directly (`from db import
get_connection`), not module-qualified like db/*.py's own submodules, so
tests patch `serial_store_aio.get_connection` rather than
`db.connection.get_connection`.
"""
import asyncio
import unittest
from unittest.mock import MagicMock, patch

import serial_store_aio as ssa


def _conn_cur():
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cur


class FetchCountsTests(unittest.TestCase):
    def test_reads_both_active_and_damaged_counts_in_one_query(self):
        conn, cur = _conn_cur()
        cur.fetchall.return_value = [("R1", 3, 1), ("R2", 0, 2)]
        with patch("serial_store_aio.get_connection", return_value=conn):
            counts = ssa._fetch_counts()
        self.assertEqual(counts, {"R1": (3, 1), "R2": (0, 2)})
        cur.execute.assert_called_once()
        sql_text = str(cur.execute.call_args.args[0])
        self.assertIn("activate", sql_text)
        self.assertIn("is_damaged", sql_text)


class ApplyCountsTests(unittest.TestCase):
    def test_writes_both_columns_and_resets_everything_else(self):
        conn, cur = _conn_cur()
        # sql.Composed.as_string(cur) -- used to turn the UPDATE ... VALUES
        # template into plain text for execute_values -- does an internal
        # isinstance check against a real psycopg2 cursor that no mock can
        # satisfy; stub it out, since it's psycopg2's own quoting, not ours
        # to verify here.
        with patch("serial_store_aio.get_connection", return_value=conn), \
                patch("serial_store_aio.execute_values") as execute_values, \
                patch("psycopg2.sql.Composed.as_string", return_value="UPDATE stub"):
            ssa._apply_counts({"R1": (3, 1), "R2": (0, 2)})

        values_rows = execute_values.call_args.args[2]
        self.assertEqual(sorted(values_rows), [("R1", 3, 1), ("R2", 0, 2)])

        reset_sql, reset_params = cur.execute.call_args.args
        self.assertIn("used_serials = 0", str(reset_sql))
        self.assertIn("damaged_serials = 0", str(reset_sql))
        self.assertEqual(reset_params, (("R1", "R2"),))
        conn.commit.assert_called_once()

    def test_an_empty_result_resets_every_roll_no_to_zero(self):
        conn, cur = _conn_cur()
        with patch("serial_store_aio.get_connection", return_value=conn):
            ssa._apply_counts({})
        cur.execute.assert_called_once()
        sql_text = str(cur.execute.call_args.args[0])
        self.assertIn("used_serials = 0", sql_text)
        self.assertIn("damaged_serials = 0", sql_text)
        conn.commit.assert_called_once()


class SyncOnceTests(unittest.TestCase):
    def test_fetches_then_applies_and_returns_the_counts(self):
        with patch("serial_store_aio._fetch_counts", return_value={"R1": (2, 1)}) as fetch, \
                patch("serial_store_aio._apply_counts") as apply:
            result = asyncio.run(ssa.sync_serial_counts_once())
        fetch.assert_called_once_with("public")
        apply.assert_called_once_with({"R1": (2, 1)}, "public")
        self.assertEqual(result, {"R1": (2, 1)})


if __name__ == "__main__":
    unittest.main()
