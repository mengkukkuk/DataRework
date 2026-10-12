"""Rows with is_transfer set are frozen (db/transfer.py).

A grid save skips them and reports which; a whole-container delete or rename that
would reach one is refused before anything is written. The cursor is the hand-written
one from test_container_delete: a statement it was not told about fails the test.
"""
import unittest
from unittest.mock import patch

import db
from db import transfer
from db.hierarchy import ContainerDeleteError, TransferLockedError

from test_container_delete import (FLAT_COLUMNS, FLAT_ROWS, FakeConn, container_route,
                                   count, rows)


# ---------------------------------------------------------------------------
# which edits are dropped
# ---------------------------------------------------------------------------

class SplitTransferredTests(unittest.TestCase):
    ORIGINALS = {
        1: {"id": 1, "is_transfer": False},
        2: {"id": 2, "is_transfer": True},
        3: {"id": 3, "is_transfer": None},
        4: {"id": 4},  # a table without the column
    }

    def test_edits_on_transferred_rows_are_dropped_and_reported(self):
        updates = [((1,), {"a": 1}), ((2,), {"a": 2}), ((3,), {"a": 3}), ((4,), {"a": 4})]
        deletes = [(1,), (2,), (3,)]
        kept_updates, kept_deletes, skipped = transfer.split_transferred(
            self.ORIGINALS, updates, deletes)
        self.assertEqual([pk for pk, _ in kept_updates], [(1,), (3,), (4,)])
        self.assertEqual(kept_deletes, [(1,), (3,)])
        self.assertEqual(skipped, [(2,), (2,)])

    def test_an_edit_whose_row_was_not_found_is_kept(self):
        updates, deletes, skipped = transfer.split_transferred({}, [((9,), {"a": 1})], [(8,)])
        self.assertEqual((updates, deletes, skipped), ([((9,), {"a": 1})], [(8,)], []))


# ---------------------------------------------------------------------------
# grid save
# ---------------------------------------------------------------------------

GRID_COLUMNS = ["id", "unit_source_id", "unit_serial_no", "display_source_id",
                "display_serial_no", "carton_serial_no", "product_name", "is_transfer"]


def grid_route(transferred, with_flag=True):
    """Rows 1..4 exist; those in `transferred` carry is_transfer = True."""
    columns = GRID_COLUMNS if with_flag else GRID_COLUMNS[:-1]

    def row(pk):
        values = (pk, 100 + pk, f"U{pk}", None, None, None, "old")
        return values + ((pk in transferred,) if with_flag else ())

    def route(text, params):
        if text.startswith("SELECT * FROM"):
            return rows([row(pk) for pk in params[0]], columns)
        if text.startswith("UPDATE"):
            return count(1)
        return None

    return route


class GridSaveTests(unittest.TestCase):
    def save(self, updates, deletes, transferred, with_flag=True):
        conn = FakeConn(grid_route(transferred, with_flag))
        with patch("db.connection.get_connection", return_value=conn):
            skipped = db.save_grid_changes("filling_product_logs", ("id",), updates, deletes)
        return skipped, conn

    def test_a_transferred_row_is_skipped_and_the_rest_are_written(self):
        updates = [((1,), {"product_name": "new"}), ((2,), {"product_name": "new"})]
        skipped, conn = self.save(updates, [], transferred={2})

        self.assertEqual(skipped, [(2,)])
        writes = conn.writes()
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][1], ["new", 1])
        self.assertEqual(conn.commits, 1)

    def test_a_transferred_row_is_not_deleted(self):
        skipped, conn = self.save([], [(2,)], transferred={2})
        self.assertEqual(skipped, [(2,)])
        self.assertEqual(conn.writes(), [])

    def test_when_every_row_is_transferred_nothing_is_written(self):
        skipped, conn = self.save([((2,), {"product_name": "new"})], [(3,)],
                                  transferred={2, 3})
        self.assertEqual(sorted(skipped), [(2,), (3,)])
        self.assertEqual(conn.writes(), [])

    def test_nothing_is_skipped_when_no_row_is_transferred(self):
        skipped, conn = self.save([((1,), {"product_name": "new"})], [], transferred=set())
        self.assertEqual(skipped, [])
        self.assertEqual(len(conn.writes()), 1)

    def test_a_table_without_the_column_locks_nothing(self):
        skipped, conn = self.save([((1,), {"product_name": "new"})], [], transferred={1},
                                  with_flag=False)
        self.assertEqual(skipped, [])
        self.assertEqual(len(conn.writes()), 1)

    def test_a_skipped_serial_edit_does_not_reach_the_link_table(self):
        # A serial edit would mirror into staging_product_logs; on a transferred row
        # it must not even look at the links.
        skipped, conn = self.save([((2,), {"unit_serial_no": "NEW"})], [], transferred={2})
        self.assertEqual(skipped, [(2,)])
        self.assertEqual(conn.writes(), [])
        self.assertEqual(conn.asked("staging_product_logs"), [])


# ---------------------------------------------------------------------------
# container delete
# ---------------------------------------------------------------------------

def locked_delete_route(flags):
    """Display D1's six rows, flagged by `flags` (one bool per row)."""
    base = container_route()
    flat = [row + (flag,) for row, flag in zip(FLAT_ROWS, flags)]

    def route(text, params):
        if text.startswith("SELECT * FROM"):
            return rows(flat, FLAT_COLUMNS + ["is_transfer"])
        return base(text, params)

    return route


class ContainerDeleteTests(unittest.TestCase):
    def test_a_container_holding_a_transferred_row_is_not_deleted(self):
        conn = FakeConn(locked_delete_route([False, False, True, False, False, False]))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(TransferLockedError) as caught:
                db.delete_container("display", "D1")
        self.assertIn("1 of its 6", str(caught.exception))
        self.assertEqual(conn.writes(), [])
        self.assertEqual(conn.commits, 0)

    def test_the_preview_refuses_too_so_the_user_hears_before_confirming(self):
        conn = FakeConn(locked_delete_route([True] * 6))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(TransferLockedError):
                db.container_delete_preview("display", "D1")

    def test_the_delete_ui_already_handles_it(self):
        self.assertTrue(issubclass(TransferLockedError, ContainerDeleteError))

    def test_an_untouched_container_is_still_deleted(self):
        conn = FakeConn(locked_delete_route([False] * 6))
        with patch("db.connection.get_connection", return_value=conn):
            result = db.delete_container("display", "D1")
        self.assertEqual(result["rows"], 6)
        self.assertEqual(conn.commits, 1)


# ---------------------------------------------------------------------------
# container rename
# ---------------------------------------------------------------------------

def rename_route(flags):
    def route(text, params):
        if text.startswith("SELECT 1 FROM"):
            return rows([])  # the new serial is free
        if "FILTER" in text:
            return rows([(2, 2)])
        if text.startswith("SELECT * FROM"):
            return rows([(n + 1, "D1", flag) for n, flag in enumerate(flags)],
                        ["id", "display_serial_no", "is_transfer"])
        if text.startswith("SELECT count(*) FROM"):
            return rows([(len(flags),)])
        return None

    return route


class ContainerRenameTests(unittest.TestCase):
    def test_a_container_holding_a_transferred_row_is_not_renamed(self):
        conn = FakeConn(rename_route([False, True]))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(TransferLockedError):
                db.rename_container("display", "D1", "D2")
        self.assertEqual(conn.writes(), [])
        self.assertEqual(conn.commits, 0)

    def test_a_batch_rename_is_refused_whole(self):
        conn = FakeConn(rename_route([True]))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(TransferLockedError):
                db.rename_children([("display", "D1", "D2")])
        self.assertEqual(conn.writes(), [])
        self.assertEqual(conn.commits, 0)

    def test_the_preview_refuses_before_the_user_confirms(self):
        conn = FakeConn(rename_route([True]))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(TransferLockedError):
                db.container_rename_preview("display", "D1")

    def test_the_preview_of_an_untouched_container_still_counts(self):
        conn = FakeConn(rename_route([False, False]))
        with patch("db.connection.get_connection", return_value=conn):
            self.assertEqual(db.container_rename_preview("display", "D1"),
                             {"rows": 2, "edges": 4})


if __name__ == "__main__":
    unittest.main()
