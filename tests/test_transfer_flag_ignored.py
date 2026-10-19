"""The is_transfer flag no longer locks a row.

Grid saves, grid deletes and container deletes go through for rows flagged
is_transfer, exactly as for unflagged ones. Uses the hand-written cursor from
test_container_delete: a statement it was not told about fails the test.
"""
import unittest
from unittest.mock import patch

import db

from test_container_delete import (FLAT_COLUMNS, FLAT_ROWS, FakeConn, container_route,
                                   count, rows)

GRID_COLUMNS = ["id", "unit_source_id", "unit_serial_no", "display_source_id",
                "display_serial_no", "carton_serial_no", "product_name", "is_transfer"]


def grid_route(transferred):
    """Rows 1..4 exist; those in `transferred` carry is_transfer = True."""
    def row(pk):
        return (pk, 100 + pk, f"U{pk}", None, None, None, "old", pk in transferred)

    def route(text, params):
        if text.startswith("SELECT * FROM"):
            return rows([row(pk) for pk in params[0]], GRID_COLUMNS)
        if text.startswith("UPDATE"):
            return count(1)
        if text.startswith("DELETE FROM"):
            if "RETURNING id" in text:
                return rows([(link_id,) for link_id in params[0]])
            return count(1)
        if text.startswith("SELECT COUNT(*) FROM"):
            return rows([(0,)])  # the unit link has no other row on it
        if text.startswith("SELECT roll_no FROM"):
            return rows([("R1",)])
        if text.startswith("SELECT c.serial FROM unnest"):
            return rows([])  # no container is left empty
        return None

    return route


class GridSaveTests(unittest.TestCase):
    def save(self, updates, deletes, transferred):
        conn = FakeConn(grid_route(transferred))
        with patch("db.connection.get_connection", return_value=conn):
            result = db.save_grid_changes("filling_product_logs", ("id",), updates, deletes)
        return result, conn

    def test_a_transferred_row_is_updated_like_any_other(self):
        updates = [((1,), {"product_name": "new"}), ((2,), {"product_name": "new"})]
        result, conn = self.save(updates, [], transferred={2})
        self.assertIsNone(result)
        self.assertEqual([w[1] for w in conn.writes()], [["new", 1], ["new", 2]])
        self.assertEqual(conn.commits, 1)

    def test_a_transferred_row_is_deleted(self):
        _, conn = self.save([], [(2,)], transferred={2})
        deleted_from = [text for text, _ in conn.writes()
                        if text.startswith("DELETE") and "filling_product_logs" in text]
        self.assertEqual(len(deleted_from), 1)
        self.assertEqual(conn.commits, 1)

    def test_a_serial_edit_on_a_transferred_row_reaches_the_link_table(self):
        _, conn = self.save([((2,), {"unit_serial_no": "NEW"})], [], transferred={2})
        self.assertTrue(conn.asked("staging_product_logs"))
        self.assertEqual(conn.commits, 1)


class ContainerDeleteTests(unittest.TestCase):
    def test_a_container_holding_transferred_rows_is_deleted(self):
        base = container_route()
        flat = [row + (True,) for row in FLAT_ROWS]

        def route(text, params):
            if text.startswith("SELECT * FROM"):
                return rows(flat, FLAT_COLUMNS + ["is_transfer"])
            return base(text, params)

        conn = FakeConn(route)
        with patch("db.connection.get_connection", return_value=conn):
            result = db.delete_container("display", "D1")
        self.assertEqual(result["rows"], 6)
        self.assertEqual(conn.commits, 1)


if __name__ == "__main__":
    unittest.main()
