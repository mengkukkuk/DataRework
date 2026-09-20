import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import MagicMock, patch, call

import psycopg2
import psycopg2.errors

import db
import db.connection
import db.hierarchy
import db.queries


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_conn_cur():
    """Return (mock_conn, mock_cur) wired so conn.cursor().__enter__() == cur."""
    cur = MagicMock(name="cur")
    conn = MagicMock(name="conn")
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def _sql_strings(cur):
    """Return a list of the rendered SQL text passed to each cur.execute() call."""
    result = []
    for c in cur.execute.call_args_list:
        args = c[0]  # positional args tuple
        query = args[0]
        try:
            # psycopg2.sql.Composed objects have an as_string method, but in
            # tests the cursor is a MagicMock so we use a fake DSN-less mogrify.
            # Instead we rely on the string representation of the Composed object
            # which includes the unquoted SQL template, sufficient for substring
            # checks.
            rendered = str(query)
        except Exception:
            rendered = repr(query)
        result.append(rendered)
    return result


def _make_realistic_cur():
    """
    Build a mock cursor pre-loaded with the side_effect sequences needed for
    save_grid_changes with updates=[((1,), {"unit_serial_no": "NEW_SERIAL"})].

    Call order through _update_staging_serial_data + _save_changes:
      execute #1  _fetch_rows_by_pk          SELECT *
      execute #2  _count_edge_siblings        SELECT COUNT(*)
      execute #3  _apply_edge_change          UPDATE staging_product_logs  (child_edge=99)
      execute #4  _set_serial_active OLD      UPDATE staging_serial_data   (False)
      execute #5  _set_serial_active NEW      UPDATE staging_serial_data   (True)
      execute #6  _save_changes               UPDATE filling_product_logs

    fetchall is called once (after execute #1).
    fetchone  is called once (after execute #2).
    """
    cur = MagicMock(name="cur")

    # Column names for the SELECT * result
    col_names = ["id", "unit_source_id", "unit_serial_no",
                 "display_source_id", "display_serial_no", "carton_serial_no"]

    # Build descriptor objects so cur.description[i][0] == col_names[i]
    descriptors = []
    for name in col_names:
        d = MagicMock()
        d.__getitem__ = lambda self, i, n=name: n if i == 0 else None
        descriptors.append(d)

    # One DB row: id=1, unit_source_id=99 (non-None edge), unit_serial_no="OLD_SERIAL"
    db_row = (1, 99, "OLD_SERIAL", None, None, None)

    # description is only meaningful after the first execute (SELECT *); after
    # that it isn't read again so a fixed value is fine.
    cur.description = descriptors

    # fetchall returns the single row; only called once
    cur.fetchall.return_value = [db_row]

    # fetchone returns the sibling count; only called once (0 → not shared → no error)
    cur.fetchone.return_value = (0,)

    return cur


# ---------------------------------------------------------------------------
# 1. Connection routing
# ---------------------------------------------------------------------------

class TestConnectionRouting(unittest.TestCase):
    """Every public op that opens a connection must go through
    db.connection.get_connection, not through psycopg2.connect directly.

    If a submodule had captured `get_connection` at import time,
    _test_container_rename.py's monkey-patch would not reach it and renames
    would commit to the live production DB instead of being rolled back.
    """

    def setUp(self):
        self.sentinel = _make_conn_cur()[0]
        self.get_conn_patcher = patch(
            "db.connection.get_connection", return_value=self.sentinel
        )
        self.get_conn_mock = self.get_conn_patcher.start()

        # If psycopg2.connect is ever reached the test fails loudly.
        self.pg_patcher = patch(
            "psycopg2.connect",
            side_effect=AssertionError(
                "psycopg2.connect reached — module captured get_connection at import"
            ),
        )
        self.pg_patcher.start()

    def tearDown(self):
        patch.stopall()

    def _call(self, fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
        except AssertionError:
            raise  # let the guard fire loudly
        except Exception:
            pass  # Only routing matters, not the result.

    def _assert_never_connected_directly(self):
        """psycopg2.connect must never have been called."""
        # The patcher raises AssertionError on any call, so if we reach here
        # without that error the mock was simply never invoked. Double-check
        # by inspecting the mock object the patcher injected.
        import unittest.mock as _mock
        pg_mock = _mock.patch.object.__class__  # noqa — we use patch.stopall ordering
        # Retrieve the live mock through the patcher's attribute
        for p in self.pg_patcher, :
            m = getattr(p, "new", None)
            if m is not None:
                m.assert_not_called()

    def test_get_columns_routes_through_get_connection(self):
        self._call(db.get_columns, "some_table")
        self.get_conn_mock.assert_called()

    def test_get_primary_key_columns_routes_through_get_connection(self):
        self._call(db.get_primary_key_columns, "some_table")
        self.get_conn_mock.assert_called()

    def test_fetch_distinct_values_routes_through_get_connection(self):
        self._call(db.fetch_distinct_values, "some_table", "some_col")
        self.get_conn_mock.assert_called()

    def test_query_rows_routes_through_get_connection(self):
        self._call(db.query_rows, "some_table", ["id"], [])
        self.get_conn_mock.assert_called()

    def test_save_changes_routes_through_get_connection(self):
        self._call(db.save_changes, "some_table", ("id",), [], [])
        self.get_conn_mock.assert_called()

    def test_authenticate_routes_through_get_connection(self):
        self._call(db.authenticate, "user", "pass")
        self.get_conn_mock.assert_called()

    def test_update_staging_serial_data_routes_through_get_connection(self):
        # Non-empty input required to open a connection.
        self._call(
            db.update_staging_serial_data,
            updates=[((1,), {"unit_serial_no": "NEW"})],
            deletes=[],
            pk_columns=("id",),
        )
        self.get_conn_mock.assert_called()

    def test_save_grid_changes_routes_through_get_connection(self):
        self._call(
            db.save_grid_changes,
            table="filling_product_logs",
            pk_columns=("id",),
            updates=[((1,), {"unit_serial_no": "NEW"})],
            deletes=[],
        )
        self.get_conn_mock.assert_called()

    def test_container_serials_routes_through_get_connection(self):
        self._call(db.container_serials, "display")
        self.get_conn_mock.assert_called()

    def test_container_children_routes_through_get_connection(self):
        self._call(db.container_children, "display", "D001")
        self.get_conn_mock.assert_called()

    def test_rename_children_routes_through_get_connection(self):
        # Non-empty batch to reach the DB path.
        self._call(db.rename_children, [("display", "D001", "D002")])
        self.get_conn_mock.assert_called()

    def test_container_rename_preview_routes_through_get_connection(self):
        self._call(db.container_rename_preview, "display", "D001")
        self.get_conn_mock.assert_called()

    def test_rename_container_routes_through_get_connection(self):
        self._call(db.rename_container, "display", "D001", "D002")
        self.get_conn_mock.assert_called()


# ---------------------------------------------------------------------------
# 2. Exception identity
# ---------------------------------------------------------------------------

class TestExceptionIdentity(unittest.TestCase):
    """The facade re-exports must be the exact same objects as the hierarchy
    module defines, so `except db.SharedEdgeError` in main_window.py still
    catches exceptions raised deep inside the package."""

    def test_shared_edge_error_is_same_object(self):
        self.assertIs(db.SharedEdgeError, db.hierarchy.SharedEdgeError)

    def test_serial_conflict_error_is_same_object(self):
        self.assertIs(db.SerialConflictError, db.hierarchy.SerialConflictError)


# ---------------------------------------------------------------------------
# 3. save_grid_changes: empty input
# ---------------------------------------------------------------------------

class TestSaveGridChangesEmpty(unittest.TestCase):
    def test_empty_updates_and_deletes_returns_none_without_connection(self):
        with patch("db.connection.get_connection") as mock_gc:
            result = db.save_grid_changes("filling_product_logs", ("id",), [], [])
        self.assertIsNone(result)
        mock_gc.assert_not_called()


# ---------------------------------------------------------------------------
# 4. save_grid_changes: success path
# ---------------------------------------------------------------------------

class TestSaveGridChangesSuccess(unittest.TestCase):
    def test_one_connection_one_cursor_one_commit_no_rollback(self):
        conn, _ = _make_conn_cur()
        cur = _make_realistic_cur()
        # Wire the realistic cursor into the mock connection
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("db.connection.get_connection", return_value=conn):
            db.save_grid_changes(
                table="filling_product_logs",
                pk_columns=("id",),
                updates=[((1,), {"unit_serial_no": "NEW_SERIAL"})],
                deletes=[],
                tag_name="TEST-OPERATOR",
            )

        # One connection, one cursor context entered.
        conn.cursor.assert_called_once()

        # Gather the SQL text of every execute call.
        sqls = _sql_strings(cur)

        # The mirror phase must have written to staging_product_logs (edge UPDATE
        # from _apply_edge_change) — unit is index 0, so child_edge=99, parent_edge=None.
        mirror_edge_writes = [s for s in sqls if "staging_product_logs" in s and "UPDATE" in s]
        self.assertTrue(
            mirror_edge_writes,
            f"Expected an UPDATE on staging_product_logs from _apply_edge_change; got: {sqls}"
        )

        # Both _set_serial_active UPDATEs on staging_serial_data must appear.
        serial_data_writes = [s for s in sqls if "staging_serial_data" in s and "UPDATE" in s]
        serial_params = [
            call.args[1] for statement, call in zip(sqls, cur.execute.call_args_list)
            if "staging_serial_data" in statement and "UPDATE" in statement
        ]
        self.assertEqual(serial_params, [
            (False, "TEST-OPERATOR", "OLD_SERIAL"),
            (True, "TEST-OPERATOR", "NEW_SERIAL"),
        ])
        self.assertTrue(all("activate_by" in statement for statement in serial_data_writes))
        # Matched on the trimmed serial: staging_serial_data stores a trailing space.
        self.assertTrue(all("btrim" in statement for statement in serial_data_writes))
        self.assertEqual(
            len(serial_data_writes), 2,
            f"Expected exactly 2 UPDATEs on staging_serial_data (old→False, new→True); got: {sqls}"
        )

        # The grid phase must have written to filling_product_logs.
        grid_writes = [s for s in sqls if "filling_product_logs" in s and "UPDATE" in s]
        self.assertTrue(
            grid_writes,
            f"Expected an UPDATE on filling_product_logs from _save_changes; got: {sqls}"
        )

        # The same cursor object served both phases — the fixture cur is the one
        # that received all execute calls, so simply check it was used at all.
        self.assertGreater(cur.execute.call_count, 0)

        # Exactly one commit, zero rollbacks.
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()


# ---------------------------------------------------------------------------
# 5. save_grid_changes: failure in grid phase after successful mirror
# ---------------------------------------------------------------------------

class TestSaveGridChangesGridFailure(unittest.TestCase):
    def test_rollback_called_commit_not_called_exception_propagates(self):
        conn, _ = _make_conn_cur()
        cur = _make_realistic_cur()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        boom = RuntimeError("grid exploded")

        with patch("db.connection.get_connection", return_value=conn):
            with patch("db.queries._save_changes", side_effect=boom):
                with self.assertRaises(RuntimeError) as ctx:
                    db.save_grid_changes(
                        table="filling_product_logs",
                        pk_columns=("id",),
                        updates=[((1,), {"unit_serial_no": "NEW_SERIAL"})],
                        deletes=[],
                    )

        self.assertIs(ctx.exception, boom)

        # The mirror writes must have occurred BEFORE the injected failure.
        sqls = _sql_strings(cur)

        mirror_edge_writes = [s for s in sqls if "staging_product_logs" in s and "UPDATE" in s]
        self.assertTrue(
            mirror_edge_writes,
            f"Mirror edge write (staging_product_logs UPDATE) must precede grid failure; got: {sqls}"
        )

        serial_data_writes = [s for s in sqls if "staging_serial_data" in s and "UPDATE" in s]
        self.assertEqual(
            len(serial_data_writes), 2,
            f"Both staging_serial_data UPDATEs must precede grid failure; got: {sqls}"
        )

        # Rollback called, commit not called.
        conn.rollback.assert_called()
        conn.commit.assert_not_called()


# ---------------------------------------------------------------------------
# 6. UniqueViolation -> SerialConflictError
# ---------------------------------------------------------------------------

class TestSaveGridChangesUniqueViolation(unittest.TestCase):
    def _run_expecting_serial_conflict(self, patch_target, uv):
        conn, cur = _make_conn_cur()
        desc_col = MagicMock()
        desc_col.__getitem__ = lambda self, i: "id" if i == 0 else None
        cur.description = [desc_col]
        cur.fetchall.return_value = []

        with patch("db.connection.get_connection", return_value=conn):
            with patch(patch_target, side_effect=uv):
                with self.assertRaises(db.SerialConflictError) as ctx:
                    db.save_grid_changes(
                        table="filling_product_logs",
                        pk_columns=("id",),
                        updates=[((1,), {"unit_serial_no": "NEW"})],
                        deletes=[],
                    )
        exc = ctx.exception
        self.assertIs(exc.__cause__, uv)
        self.assertIn("That serial already exists", str(exc))
        conn.rollback.assert_called()
        conn.commit.assert_not_called()

    def test_unique_violation_from_grid_phase_becomes_serial_conflict_error(self):
        uv = psycopg2.errors.UniqueViolation("duplicate key value")
        self._run_expecting_serial_conflict("db.queries._save_changes", uv)

    def test_unique_violation_from_commit_becomes_serial_conflict_error(self):
        conn, cur = _make_conn_cur()
        desc_col = MagicMock()
        desc_col.__getitem__ = lambda self, i: "id" if i == 0 else None
        cur.description = [desc_col]
        cur.fetchall.return_value = []

        uv = psycopg2.errors.UniqueViolation("duplicate key at commit")
        conn.commit.side_effect = uv

        with patch("db.connection.get_connection", return_value=conn):
            with patch("db.queries._save_changes"):
                with self.assertRaises(db.SerialConflictError) as ctx:
                    db.save_grid_changes(
                        table="filling_product_logs",
                        pk_columns=("id",),
                        updates=[((1,), {"unit_serial_no": "NEW"})],
                        deletes=[],
                    )
        exc = ctx.exception
        self.assertIs(exc.__cause__, uv)
        self.assertIn("That serial already exists", str(exc))


# ---------------------------------------------------------------------------
# 7. OperationalError propagates unchanged
# ---------------------------------------------------------------------------

class TestSaveGridChangesOperationalError(unittest.TestCase):
    def test_operational_error_propagates_unchanged(self):
        conn, cur = _make_conn_cur()
        oe = psycopg2.OperationalError("connection refused")
        # Raise before any cursor work so there is no description/fetchall needed.
        conn.cursor.return_value.__enter__.side_effect = oe

        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(psycopg2.OperationalError) as ctx:
                db.save_grid_changes(
                    table="filling_product_logs",
                    pk_columns=("id",),
                    updates=[((1,), {"unit_serial_no": "NEW"})],
                    deletes=[],
                )
        self.assertIs(ctx.exception, oe)


# ---------------------------------------------------------------------------
# 8. SharedEdgeError raised before any write
# ---------------------------------------------------------------------------

class TestSaveGridChangesSharedEdge(unittest.TestCase):
    """_update_staging_serial_data completes its full validation pass
    (including counting siblings) and raises SharedEdgeError *before* any
    UPDATE or DELETE touches filling_product_logs or the edge table, and
    before commit() is called."""

    def test_shared_edge_raises_before_write_and_before_commit(self):
        conn, cur = _make_conn_cur()

        # Two sequential selects happen inside _update_staging_serial_data:
        #
        #   1. _fetch_rows_by_pk  → SELECT * ... WHERE id = ANY(...)
        #      cur.description must list column names; cur.fetchall() returns rows.
        #      We need "id" and "unit_source_id" so the validator can find the
        #      edge_id for the "unit" level being edited.
        #
        #   2. _count_edge_siblings → SELECT COUNT(*) ...
        #      cur.fetchone() returns (N,); we return (2,) to trigger the block.
        #
        # We track execute call count to return the right shape each time.

        col_names = ["id", "unit_source_id", "unit_serial_no",
                     "display_source_id", "display_serial_no", "carton_serial_no"]
        db_row = [1, 99, "OLD", None, None, None]

        execute_calls = [0]

        def fake_execute(query, params=None):
            execute_calls[0] += 1

        # Build descriptor objects whose [0] index yields the column name.
        descriptors = []
        for name in col_names:
            d = MagicMock()
            d.__getitem__ = lambda self, i, n=name: n if i == 0 else None
            descriptors.append(d)

        def description_prop(self_ignored):
            # After the first execute (SELECT *) return column descriptors.
            # After subsequent executes (COUNT) return a single-col descriptor.
            if execute_calls[0] == 1:
                return descriptors
            single = MagicMock()
            single.__getitem__ = lambda self, i: "count" if i == 0 else None
            return [single]

        type(cur).description = property(description_prop)
        cur.execute.side_effect = fake_execute
        cur.fetchall.return_value = [db_row]
        cur.fetchone.return_value = (2,)  # 2 siblings → SharedEdgeError

        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(db.SharedEdgeError):
                db.save_grid_changes(
                    table="filling_product_logs",
                    pk_columns=("id",),
                    # Editing unit_serial_no causes the validator to look up
                    # unit_source_id=99 and count its siblings.
                    updates=[((1,), {"unit_serial_no": "NEW"})],
                    deletes=[],
                )

        # SharedEdgeError is raised before any write and before commit.
        conn.commit.assert_not_called()
        # execute was called for the two SELECTs only — no UPDATE/DELETE.
        # (We cannot inspect SQL text through a MagicMock side_effect, but
        # the unit_serial_no column never appears in filling_product_logs
        # directly — the only writes are to staging_product_logs via
        # _apply_edge_change, which is never reached when the validator fires.)
        self.assertEqual(execute_calls[0], 2)


if __name__ == "__main__":
    unittest.main()
