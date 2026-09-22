"""_apply_serial_rename (db/containers.py): a rename carries the new serial's
roll_no along with it, into both edges and the flat table.

staging_serial_data maps serial_no -> roll_no; nothing else keeps
filling_product_logs.<level>_roll_no or staging_product_logs'
source_roll_no/target_roll_no in step with a renamed serial, so
_apply_serial_rename looks the new roll_no up itself and writes it everywhere
the serial itself lands.
"""
import unittest
from unittest.mock import MagicMock

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


if __name__ == "__main__":
    unittest.main()
