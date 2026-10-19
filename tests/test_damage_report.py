"""db.report_damage and db.serial_level: the backend for the Report damage tab.

report_damage refuses while a serial is still active (SerialInUseError) or
unknown to inventory (SerialInventoryError); serial_level is the best-effort
lookup used to route an operator to the right editor when blocked.
"""
import datetime
import unittest
from unittest.mock import MagicMock, patch

import db
from db.hierarchy import SerialInUseError, SerialInventoryError


def _conn_cur(fetchone_value):
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_value
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cur


class ReportDamageTests(unittest.TestCase):
    def test_an_unknown_serial_is_refused(self):
        conn, cur = _conn_cur(None)
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(SerialInventoryError) as ctx:
                db.report_damage("NOPE")
        self.assertIn("NOPE", str(ctx.exception))
        cur.execute.assert_called_once()  # only the read; no UPDATE was attempted
        conn.commit.assert_not_called()

    def test_a_still_active_serial_is_refused_and_nothing_is_written(self):
        conn, cur = _conn_cur(("R1", True))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(SerialInUseError) as ctx:
                db.report_damage("U1")
        self.assertIn("U1", str(ctx.exception))
        cur.execute.assert_called_once()
        conn.commit.assert_not_called()

    def test_an_inactive_serial_is_flagged_damaged(self):
        conn, cur = _conn_cur(("R1", False))
        cur.rowcount = 1
        with patch("db.connection.get_connection", return_value=conn):
            result = db.report_damage("U1")
        self.assertEqual(result, {"serial_no": "U1", "roll_no": "R1"})
        self.assertEqual(cur.execute.call_count, 2)
        update_sql, update_params = cur.execute.call_args_list[1].args
        self.assertIn("is_damaged", str(update_sql))
        self.assertIn("is_damaged_at = now()", str(update_sql))  # when it was reported
        self.assertIn("activate = false", str(update_sql))
        self.assertEqual(update_params, ("U1",))
        conn.commit.assert_called_once()

    def test_going_active_between_the_read_and_the_write_is_refused_not_reported(self):
        # The read saw activate=false, but the guarded UPDATE matched nothing --
        # someone reactivated it in between. Must not report a false success.
        conn, cur = _conn_cur(("R1", False))
        cur.rowcount = 0
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(SerialInUseError):
                db.report_damage("U1")
        conn.commit.assert_not_called()

    def test_a_blank_serial_is_refused_before_any_connection(self):
        with patch("db.connection.get_connection") as get_conn:
            with self.assertRaises(ValueError):
                db.report_damage("   ")
        get_conn.assert_not_called()


class ListDamagedTests(unittest.TestCase):
    ROW = ("U1", "Qr Code", "R1", "B1", None, "VM001")

    def _run(self, **kwargs):
        conn, cur = _conn_cur(None)
        cur.fetchall.return_value = [self.ROW]
        with patch("db.connection.get_connection", return_value=conn):
            result = db.list_damaged(**kwargs)
        query, params = cur.execute.call_args.args
        return result, repr(query), params

    def test_rows_come_back_as_dicts(self):
        result, _, _ = self._run()
        self.assertEqual(result, [{
            "serial_no": "U1", "level": "Qr Code", "roll_no": "R1", "box_no": "B1",
            "damaged_at": None, "last_user": "VM001"}])

    def test_no_range_means_every_damaged_serial(self):
        _, text, params = self._run()
        self.assertIn("is_damaged IS TRUE", text)
        self.assertNotIn("is_damaged_at >=", text)
        self.assertEqual(params, [])

    def test_a_range_filters_on_is_damaged_at_with_both_ends_inclusive(self):
        start, end = datetime.datetime(2026, 10, 1), datetime.datetime(2026, 10, 2)
        _, text, params = self._run(start=start, end=end)
        self.assertIn("is_damaged_at >=", text)
        self.assertIn("is_damaged_at <=", text)
        self.assertEqual(params, [start, end])

    def test_it_only_reads_and_releases_the_transaction(self):
        conn, cur = _conn_cur(None)
        cur.fetchall.return_value = []
        with patch("db.connection.get_connection", return_value=conn):
            db.list_damaged()
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()


class SerialLevelTests(unittest.TestCase):
    def _cur_finding(self, found_at):
        """A cursor whose SELECT only matches once LEVELS reaches `found_at`."""
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (1,) if level == found_at else None for level in db.LEVELS
        ]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        conn.cursor.return_value.__exit__.return_value = False
        return conn, cur

    def test_finds_a_unit_on_the_first_query(self):
        conn, cur = self._cur_finding("unit")
        with patch("db.connection.get_connection", return_value=conn):
            self.assertEqual(db.serial_level("U1"), "unit")
        self.assertEqual(cur.execute.call_count, 1)

    def test_finds_a_display_after_checking_unit_first(self):
        conn, cur = self._cur_finding("display")
        with patch("db.connection.get_connection", return_value=conn):
            self.assertEqual(db.serial_level("D1"), "display")
        self.assertEqual(cur.execute.call_count, 2)

    def test_a_serial_naming_nothing_in_the_flat_table_is_none(self):
        conn, cur = self._cur_finding(None)
        with patch("db.connection.get_connection", return_value=conn):
            self.assertIsNone(db.serial_level("GHOST"))
        self.assertEqual(cur.execute.call_count, len(db.LEVELS))

    def test_a_blank_serial_is_none_without_any_connection(self):
        with patch("db.connection.get_connection") as get_conn:
            self.assertIsNone(db.serial_level(""))
        get_conn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
