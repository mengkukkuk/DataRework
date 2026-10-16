"""_apply_serial_rename (db/containers.py): a rename carries the new serial's
roll_no along with it, into both edges and the flat table.

staging_serial_data maps serial_no -> roll_no; nothing else keeps
filling_product_logs.<level>_roll_no or staging_product_logs'
source_roll_no/target_roll_no in step with a renamed serial, so
_apply_serial_rename looks the new roll_no up itself and writes it everywhere
the serial itself lands.
"""
import unittest
from unittest.mock import MagicMock, patch

import db
from db import containers


def _sql_strings(cur):
    return [str(call.args[0]) for call in cur.execute.call_args_list]


class ApplySerialRenameRollNoTests(unittest.TestCase):
    def test_the_new_serials_roll_no_is_carried_to_both_edges_and_the_flat_table(self):
        cur = MagicMock()
        cur.fetchone.return_value = ("NEW-ROLL",)
        cur.rowcount = 7

        result = containers._apply_serial_rename(cur, "display", "D1", "D2", "public",
                                                  "filling_product_logs")

        self.assertEqual(result, 7)
        self.assertEqual(cur.execute.call_count, 4)  # lookup + 2 edges + flat
        sqls = _sql_strings(cur)
        params = [call.args[1] for call in cur.execute.call_args_list]

        lookup_sql, child_edge_sql, parent_edge_sql, flat_sql = sqls
        lookup_params, child_edge_params, parent_edge_params, flat_params = params

        self.assertIn("staging_serial_data", lookup_sql)
        self.assertIn("btrim", lookup_sql)
        self.assertEqual(lookup_params, ("D2",))

        self.assertIn("source_roll_no", child_edge_sql)
        self.assertNotIn("target_roll_no", child_edge_sql)
        self.assertEqual(child_edge_params, ["D2", "NEW-ROLL", "D1", "display"])

        self.assertIn("target_roll_no", parent_edge_sql)
        self.assertNotIn("source_roll_no", parent_edge_sql)
        self.assertEqual(parent_edge_params, ["D2", "NEW-ROLL", "D1", "display"])

        self.assertIn("display_roll_no", flat_sql)
        self.assertEqual(flat_params, ["D2", "NEW-ROLL", "D1"])

    def test_a_new_serial_with_no_inventory_row_leaves_roll_no_untouched(self):
        cur = MagicMock()
        cur.fetchone.return_value = None  # no staging_serial_data row for "D2"
        cur.rowcount = 3

        containers._apply_serial_rename(cur, "display", "D1", "D2", "public",
                                        "filling_product_logs")

        sqls = _sql_strings(cur)
        params = [call.args[1] for call in cur.execute.call_args_list]
        _lookup, child_edge_sql, parent_edge_sql, flat_sql = sqls
        _lookup_p, child_edge_params, parent_edge_params, flat_params = params

        for text in (child_edge_sql, parent_edge_sql, flat_sql):
            self.assertNotIn("roll_no", text)
        self.assertEqual(child_edge_params, ["D2", "D1", "display"])
        self.assertEqual(parent_edge_params, ["D2", "D1", "display"])
        self.assertEqual(flat_params, ["D2", "D1"])


class RenameSerialStateTests(unittest.TestCase):
    """rename_container/rename_children flip staging_serial_data.activate for
    the renamed serial at every level, not just unit -- a container's roll_no
    is counted the same way a unit's is, so its activate flag has to follow
    the serial just as reliably."""

    def test_rename_children_updates_serial_state_at_every_level_in_the_batch(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        with patch("db.connection.get_connection", return_value=conn), patch(
            "db.containers._serial_in_use", return_value=False
        ), patch("db.containers._container_edge_counts", return_value=(1, 0)), patch(
            "db.containers._apply_serial_rename", return_value=1
        ), patch("db.containers._set_serial_active") as active:
            db.rename_children([
                ("unit", "U1", "U-new"),
                ("display", "D1", "D-new"),
            ])
        self.assertEqual(
            [call.args[2:] for call in active.call_args_list],
            [("U1", False), ("U-new", True), ("D1", False), ("D-new", True)],
        )
        self.assertTrue(all(
            call.kwargs == {"required": True}
            for call in active.call_args_list[1::2]
        ))


class SetSerialActiveGuardTests(unittest.TestCase):
    """Activating a serial never touches a row already damaged or in use."""

    def test_activation_update_excludes_damaged_and_in_use_rows(self):
        from db.serial_state import _set_serial_active
        cur = MagicMock()
        cur.rowcount = 1
        _set_serial_active(cur, "public", "S1", True, required=True)
        text = _sql_strings(cur)[0]
        self.assertIn("is_damaged", text)
        self.assertIn("is_use", text)

    def test_deactivation_is_not_guarded(self):
        from db.serial_state import _set_serial_active
        cur = MagicMock()
        cur.rowcount = 1
        _set_serial_active(cur, "public", "S1", False)
        self.assertNotIn("<>", _sql_strings(cur)[0])

    def test_damaged_row_is_refused_and_says_so(self):
        from db.serial_state import _set_serial_active
        cur = MagicMock()
        cur.rowcount = 0                          # guard excluded the row
        cur.fetchall.return_value = [("true", "false")]
        with self.assertRaises(db.hierarchy.SerialUnavailableError) as ctx:
            _set_serial_active(cur, "public", "S1", True, required=True)
        self.assertIn("damaged", str(ctx.exception))
        self.assertIsInstance(ctx.exception, db.SerialInventoryError)

    def test_in_use_row_is_refused_and_says_so(self):
        from db.serial_state import _set_serial_active
        cur = MagicMock()
        cur.rowcount = 0
        cur.fetchall.return_value = [("", "true")]
        with self.assertRaises(db.hierarchy.SerialUnavailableError) as ctx:
            _set_serial_active(cur, "public", "S1", True, required=True)
        self.assertIn("already in use", str(ctx.exception))

    def test_not_required_activation_just_skips_a_blocked_row(self):
        from db.serial_state import _set_serial_active
        cur = MagicMock()
        cur.rowcount = 0
        self.assertEqual(_set_serial_active(cur, "public", "S1", True), 0)

    def test_missing_row_still_raises_when_required(self):
        from db.serial_state import _set_serial_active
        cur = MagicMock()
        cur.rowcount = 0
        cur.fetchall.return_value = []
        with self.assertRaises(db.SerialInventoryError) as ctx:
            _set_serial_active(cur, "public", "S1", True, required=True)


if __name__ == "__main__":
    unittest.main()
