"""Container deletion and grid-delete link clean-up (db/deletion.py).

The SQL itself is run against a real PostgreSQL by _test_container_delete_pg.py.
These tests pin what the code decides, what it asks the database, and the order and
atomicity of its writes. A hand-written cursor answers each statement it is told
about; any other statement fails the test.

The world used throughout: display D1 holds six units U1..U6 (links 11..16) and is
itself linked (id 10) to inner I1, whose own link (id 5) goes to carton C1.
"""
import unittest
from unittest.mock import patch

import psycopg2
from psycopg2 import sql

import db
from db import deletion
from db.hierarchy import ContainerDeleteError


# ---------------------------------------------------------------------------
# a cursor that answers statements by hand
# ---------------------------------------------------------------------------

def render(query):
    """Readable SQL text for a str or psycopg2.sql composable, without a connection."""
    if isinstance(query, str):
        return query
    if isinstance(query, sql.Composed):
        return "".join(render(part) for part in query.seq)
    if isinstance(query, sql.SQL):
        return query.string
    if isinstance(query, sql.Identifier):
        return ".".join(f'"{name}"' for name in query.strings)
    if isinstance(query, sql.Placeholder):
        return "%s"
    raise TypeError(f"cannot render {query!r}")


def rows(data, columns=None):
    return {"rows": list(data), "columns": columns}


def count(n):
    return {"count": n}


class FakeCursor:
    def __init__(self, route, events):
        self._route = route
        self._events = events
        self.statements = []
        self._rows = []
        self.description = None
        self.rowcount = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        text = render(query)
        self.statements.append((text, params))
        self._events.append(("execute", text, params))
        result = self._route(text, params)
        if result is None:
            raise AssertionError(f"unexpected SQL: {text} {params!r}")
        if "count" in result:
            self.rowcount, self._rows, self.description = result["count"], [], None
        else:
            self._rows = list(result["rows"])
            self.rowcount = len(self._rows)
            names = result["columns"]
            self.description = [(name,) for name in names] if names else None

    def fetchall(self):
        out, self._rows = self._rows, []
        return out

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class FakeConn:
    def __init__(self, route):
        self.events = []
        self.cur = FakeCursor(route, self.events)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1
        self.events.append(("commit",))

    def rollback(self):
        self.rollbacks += 1
        self.events.append(("rollback",))

    def close(self):
        self.closed = True

    def writes(self):
        return [(text, params) for text, params in self.cur.statements
                if text.lstrip().upper().startswith(("UPDATE", "DELETE", "INSERT"))]

    def asked(self, fragment):
        return [params for text, params in self.cur.statements if fragment in text]


def target(text):
    """Which of the three tables a write statement touches."""
    for name in ("staging_serial_data", "staging_product_logs"):
        if name in text:
            return name
    return "flat"


# ---------------------------------------------------------------------------
# the world
# ---------------------------------------------------------------------------

UNIT_LINKS = [(11 + n, f"U{n + 1}", "unit", "D1", "display", 1) for n in range(6)]
OWN_LINK = [(10, "I1", "inner")]
FLAT_COLUMNS = ["id", "unit_serial_no", "unit_source_id", "display_serial_no",
                "display_source_id", "inner_serial_no", "inner_source_id", "carton_serial_no"]
FLAT_ROWS = [(n + 1, f"U{n + 1}", 11 + n, "D1", 10, "I1", 5, "C1") for n in range(6)]


def container_route(*, own=OWN_LINK, inside=UNIT_LINKS, flat=FLAT_ROWS,
                    inner_stays=True, carton_stays=True, live_links=None,
                    links_deleted=None, rows_deleted=None):
    """Answers the statements emitted for deleting display D1.

    inner_stays / carton_stays: whether the parent still holds something else once
    D1 is gone. live_links: the link ids that still exist, for the check on the ids
    the saved rows point at (None means all of them do). links_deleted /
    rows_deleted override what a DELETE reports back.
    """
    parent_link = {"inner": [(5, "C1", "carton")], "carton": []}

    def route(text, params):
        if text.startswith("SELECT id FROM"):
            asked = params[0]
            return rows([(link,) for link in asked
                         if live_links is None or link in live_links])
        if "WITH RECURSIVE" in text:
            return rows(inside)
        if text.startswith("SELECT * FROM"):
            return rows(flat, FLAT_COLUMNS)
        if "unnest(" in text:
            serials, level = params[0], params[1]
            stays = {"inner": inner_stays, "carton": carton_stays}[level]
            return rows([] if stays else [(serial,) for serial in serials])
        if text.startswith("SELECT id, parent_serial_no") and "= ANY(" in text:
            return rows(parent_link[params[0]])
        if text.startswith("SELECT id, parent_serial_no"):
            return rows(own)
        if text.startswith("UPDATE"):
            return count(len(params[1]))
        if text.startswith("DELETE") and "staging_product_logs" in text:
            kept = params[0] if links_deleted is None else params[0][:links_deleted]
            return rows([(link,) for link in kept], ["id"])
        if text.startswith("DELETE"):
            return count(len(flat) if rows_deleted is None else rows_deleted)
        return None

    return route


def failing(route, when, exc):
    """`route`, except that any statement for which `when(text)` raises `exc`."""
    def wrapper(text, params):
        if when(text):
            raise exc
        return route(text, params)
    return wrapper


# ---------------------------------------------------------------------------
# the listing shown before the user confirms
# ---------------------------------------------------------------------------

class ChildrenTreeTests(unittest.TestCase):
    def test_children_follow_their_parent_with_depth_and_child_counts(self):
        # I1 holds D1 (units U1, U2) and D2 (unit U3); links arrive in no useful order.
        inside = [
            (2, "D2", "display", "I1", "inner"),
            (1, "D1", "display", "I1", "inner"),
            (5, "U3", "unit", "D2", "display"),
            (3, "U1", "unit", "D1", "display"),
            (4, "U2", "unit", "D1", "display"),
        ]
        self.assertEqual(deletion._children_tree("I1", "inner", inside), [
            {"serial_no": "D1", "level": "display", "depth": 1, "children": 2},
            {"serial_no": "U1", "level": "unit", "depth": 2, "children": 0},
            {"serial_no": "U2", "level": "unit", "depth": 2, "children": 0},
            {"serial_no": "D2", "level": "display", "depth": 1, "children": 1},
            {"serial_no": "U3", "level": "unit", "depth": 2, "children": 0},
        ])

    def test_a_link_loop_in_bad_data_lists_each_item_once(self):
        loop = [
            (1, "A", "display", "R", "inner"),
            (2, "B", "display", "A", "display"),
            (3, "A", "display", "B", "display"),
        ]
        listed = [(c["serial_no"], c["depth"]) for c in deletion._children_tree("R", "inner", loop)]
        self.assertEqual(listed, [("A", 1), ("B", 2)])


# ---------------------------------------------------------------------------
# preview: what would be deleted, decided without writing anything
# ---------------------------------------------------------------------------

class PreviewTests(unittest.TestCase):
    def preview(self, level="display", serial="D1", **world):
        conn = FakeConn(container_route(**world))
        with patch("db.connection.get_connection", return_value=conn):
            result = db.container_delete_preview(level, serial)
        return result, conn

    def test_counts_what_would_go_and_lists_what_is_inside(self):
        result, conn = self.preview()
        self.assertEqual((result["rows"], result["units"]), (6, 6))
        # D1's own link (10) and its six unit links; I1's link (5) stays with I1.
        self.assertEqual(result["edges"], 7)
        self.assertEqual(result["emptied"], [])
        self.assertEqual([c["serial_no"] for c in result["children"]],
                         ["U1", "U2", "U3", "U4", "U5", "U6"])
        self.assertEqual(conn.writes(), [])
        self.assertEqual(conn.commits, 0)

    def test_a_parent_left_empty_is_reported_and_its_link_counted(self):
        result, _ = self.preview(inner_stays=False, carton_stays=False)
        self.assertEqual(result["emptied"], [{"level": "inner", "serial_no": "I1"},
                                             {"level": "carton", "serial_no": "C1"}])
        self.assertEqual(result["edges"], 8)  # plus I1's own link (5); a carton has none

    def test_the_emptiness_check_excludes_everything_being_deleted(self):
        # Without this I1 would still "contain" D1 (link 10) and never look empty.
        _, conn = self.preview()
        self.assertEqual(
            conn.asked("unnest("),
            [(["I1"], "inner", [10, 11, 12, 13, 14, 15, 16], "D1"),
             (["C1"], "carton", [10, 11, 12, 13, 14, 15, 16], "D1")],
        )

    def test_children_with_a_link_but_no_saved_row_are_counted(self):
        stray = UNIT_LINKS + [(17, "U7", "unit", "D1", "display", 1)]
        result, _ = self.preview(inside=stray)
        self.assertEqual((result["rows"], result["units"], result["edges"]), (6, 7, 8))

    def test_a_container_with_nothing_inside_can_be_previewed(self):
        result, _ = self.preview(inside=[], flat=[])
        self.assertEqual((result["rows"], result["units"], result["edges"]), (0, 0, 1))
        self.assertEqual(result["children"], [])

    def test_only_display_inner_and_carton_can_be_deleted(self):
        for level in ("unit", "shelf"):
            with patch("db.connection.get_connection") as get_connection:
                with self.assertRaises(ValueError):
                    db.container_delete_preview(level, "X")
                get_connection.assert_not_called()

    def test_a_serial_linked_under_two_parents_is_refused(self):
        with self.assertRaises(ContainerDeleteError) as ctx:
            self.preview(own=[(10, "I1", "inner"), (20, "I2", "inner")])
        self.assertIn("more than one", str(ctx.exception))

    def test_saved_rows_spread_over_two_parents_are_refused(self):
        split = FLAT_ROWS[:5] + [(6, "U6", 16, "D1", 10, "I2", 5, "C1")]
        with self.assertRaises(ContainerDeleteError) as ctx:
            self.preview(flat=split)
        self.assertIn("more than one", str(ctx.exception))

    def test_a_container_whose_links_are_gone_still_lists_its_saved_rows(self):
        # The condition seen in production: filling_product_logs holds the rows,
        # staging_product_logs has no link of D1's own, nothing under it, and the
        # ids the rows carry name links that are not there either.
        result, _ = self.preview(own=[], inside=[], live_links=set())
        self.assertEqual((result["rows"], result["units"], result["edges"]), (6, 6, 0))
        self.assertEqual([child["serial_no"] for child in result["children"]],
                         ["U1", "U2", "U3", "U4", "U5", "U6"])
        self.assertEqual({child["level"] for child in result["children"]}, {"unit"})

    def test_saved_rows_fill_in_the_levels_between_a_carton_and_its_units(self):
        flat = [(1, "U1", 11, "D1", 10, "I1", 5, "C1"),
                (2, "U2", 12, "D1", 10, "I1", 5, "C1"),
                (3, "U3", 13, "D2", 20, "I1", 5, "C1")]
        conn = FakeConn(container_route(own=[], inside=[], flat=flat, live_links=set()))
        with patch("db.connection.get_connection", return_value=conn):
            result = db.container_delete_preview("carton", "C1")
        self.assertEqual([(c["serial_no"], c["level"], c["depth"], c["children"])
                          for c in result["children"]],
                         [("I1", "inner", 1, 2), ("D1", "display", 2, 2),
                          ("U1", "unit", 3, 0), ("U2", "unit", 3, 0),
                          ("D2", "display", 2, 1), ("U3", "unit", 3, 0)])

    def test_a_level_the_rows_leave_empty_is_a_gap_not_a_container(self):
        # No display on these rows: the units belong to the inner directly, and
        # nothing called "None" is ever listed.
        flat = [(1, "U1", 11, None, None, "I1", 5, "C1"),
                (2, "U2", 12, "", None, "I1", 5, "C1")]
        conn = FakeConn(container_route(own=[], inside=[], flat=flat, live_links=set()))
        with patch("db.connection.get_connection", return_value=conn):
            result = db.container_delete_preview("inner", "I1")
        self.assertEqual([(c["serial_no"], c["level"], c["depth"])
                          for c in result["children"]],
                         [("U1", "unit", 1), ("U2", "unit", 1)])

    def test_a_link_a_row_points_at_but_that_is_gone_is_left_out_of_the_count(self):
        # U1's row still names link 99, deleted long ago; planning to delete it
        # would make the plan's own count unreachable and abort the whole delete.
        stale = [(1, "U1", 99, "D1", 10, "I1", 5, "C1")] + FLAT_ROWS[1:]
        result, conn = self.preview(flat=stale, live_links=set())
        self.assertEqual(result["edges"], 7)  # D1's own link and links 12..16
        self.assertEqual(result["orphans"], 1)
        self.assertEqual(conn.asked("SELECT id FROM"), [([99],)])

    def test_links_the_rows_point_at_that_do_exist_are_counted(self):
        # U1 sits under D1 by link 99, which the recursive read missed.
        stale = [(1, "U1", 99, "D1", 10, "I1", 5, "C1")] + FLAT_ROWS[1:]
        result, _ = self.preview(flat=stale, live_links={99})
        self.assertEqual((result["edges"], result["orphans"]), (8, 0))

    def test_a_serial_that_names_nothing_is_refused(self):
        with self.assertRaises(ContainerDeleteError) as ctx:
            self.preview(own=[], inside=[], flat=[])
        self.assertIn('No display named "D1"', str(ctx.exception))


# ---------------------------------------------------------------------------
# delete_container: one transaction, or nothing
# ---------------------------------------------------------------------------

class DeleteContainerTests(unittest.TestCase):
    def delete(self, world=None, **kwargs):
        conn = FakeConn(container_route(**(world or {})))
        with patch("db.connection.get_connection", return_value=conn):
            result = db.delete_container("display", "D1", **kwargs)
        return result, conn

    def test_deletes_links_rows_and_releases_unit_serials_in_one_transaction(self):
        result, conn = self.delete(tag_name="OP-1")
        writes = {target(text): params for text, params in conn.writes()}
        self.assertEqual(len(conn.writes()), 3)
        self.assertEqual(writes["staging_serial_data"],
                         ("OP-1", ["U1", "U2", "U3", "U4", "U5", "U6"]))
        self.assertEqual(writes["staging_product_logs"], ([10, 11, 12, 13, 14, 15, 16],))
        self.assertEqual(writes["flat"], ("D1",))
        self.assertEqual((conn.commits, conn.rollbacks), (1, 0))
        self.assertEqual(conn.events[-1], ("commit",))
        self.assertTrue(conn.closed)
        self.assertEqual(result, {"rows": 6, "edges": 7, "units": 6, "emptied": [],
                                  "orphans": 0})

    def test_parents_left_empty_are_deleted_too(self):
        result, conn = self.delete(world={"inner_stays": False})
        links = [p for t, p in conn.writes() if target(t) == "staging_product_logs"]
        self.assertEqual(links, [([5, 10, 11, 12, 13, 14, 15, 16],)])
        self.assertEqual(result["emptied"], [{"level": "inner", "serial_no": "I1"}])

    def test_children_without_a_saved_row_are_deleted_and_released_too(self):
        stray = UNIT_LINKS + [(17, "U7", "unit", "D1", "display", 1)]
        result, conn = self.delete(world={"inside": stray})
        writes = {target(text): params for text, params in conn.writes()}
        self.assertEqual(writes["staging_serial_data"][1][-1], "U7")
        self.assertIn(17, writes["staging_product_logs"][0])
        self.assertEqual((result["units"], result["edges"]), (7, 8))

    def test_an_empty_container_releases_no_serials(self):
        result, conn = self.delete(world={"inside": [], "flat": []})
        self.assertEqual({target(text) for text, _ in conn.writes()},
                         {"staging_product_logs", "flat"})
        self.assertEqual((result["rows"], result["edges"], result["units"]), (0, 1, 0))
        self.assertEqual(conn.commits, 1)

    def test_a_stale_preview_is_refused_before_any_write(self):
        conn = FakeConn(container_route())
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(ContainerDeleteError) as ctx:
                db.delete_container("display", "D1",
                                    expected={"rows": 5, "edges": 7, "units": 5})
        self.assertIn("changed", str(ctx.exception))
        self.assertEqual(conn.writes(), [])
        self.assertEqual(conn.commits, 0)

    def test_a_matching_preview_lets_the_delete_through(self):
        result, conn = self.delete(expected={"rows": 6, "edges": 7, "units": 6})
        self.assertEqual(conn.commits, 1)
        self.assertEqual(result["rows"], 6)

    def test_a_link_a_row_points_at_but_that_is_gone_does_not_block_the_delete(self):
        stale = [(1, "U1", 99, "D1", 10, "I1", 5, "C1")] + FLAT_ROWS[1:]
        result, conn = self.delete(world={"flat": stale, "live_links": set()})
        links = [p for t, p in conn.writes() if target(t) == "staging_product_logs"]
        self.assertEqual(links, [([10, 11, 12, 13, 14, 15, 16],)])
        self.assertEqual((conn.commits, result["edges"]), (1, 7))

    def test_fewer_links_deleted_than_planned_rolls_everything_back(self):
        # Someone else removed a link between the plan and the DELETE.
        conn = FakeConn(container_route(links_deleted=6))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(ContainerDeleteError):
                db.delete_container("display", "D1")
        self.assertEqual(conn.commits, 0)
        self.assertGreaterEqual(conn.rollbacks, 1)

    def test_a_different_number_of_rows_deleted_than_planned_rolls_everything_back(self):
        # A row joined the container between the plan and the DELETE.
        conn = FakeConn(container_route(rows_deleted=7))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(ContainerDeleteError):
                db.delete_container("display", "D1")
        self.assertEqual(conn.commits, 0)
        self.assertGreaterEqual(conn.rollbacks, 1)

    def test_database_errors_roll_back_and_propagate_unchanged(self):
        lost = psycopg2.OperationalError("connection lost")
        route = failing(container_route(), lambda text: target(text) == "flat"
                        and text.startswith("DELETE"), lost)
        conn = FakeConn(route)
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(psycopg2.OperationalError) as ctx:
                db.delete_container("display", "D1")
        self.assertIs(ctx.exception, lost)
        self.assertEqual(conn.commits, 0)
        self.assertGreaterEqual(conn.rollbacks, 1)
        self.assertTrue(conn.closed)

    def test_a_link_lost_between_the_plan_and_the_delete_is_named(self):
        conn = FakeConn(container_route(links_deleted=6))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(ContainerDeleteError) as ctx:
                db.delete_container("display", "D1")
        message = str(ctx.exception)
        self.assertIn("16", message)  # the one link the DELETE did not find
        self.assertIn("Nothing was deleted", message)

    def test_a_row_count_mismatch_says_what_the_two_numbers_were(self):
        conn = FakeConn(container_route(rows_deleted=7))
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(ContainerDeleteError) as ctx:
                db.delete_container("display", "D1")
        self.assertIn("7 row(s) deleted, 6 planned", str(ctx.exception))

    def test_a_database_refusal_is_reported_as_a_delete_error(self):
        refused = psycopg2.errors.ForeignKeyViolation(
            'update or delete on table "staging_product_logs" violates foreign key')
        route = failing(container_route(), lambda text: text.startswith("DELETE")
                        and "staging_product_logs" in text, refused)
        conn = FakeConn(route)
        with patch("db.connection.get_connection", return_value=conn):
            with self.assertRaises(ContainerDeleteError) as ctx:
                db.delete_container("display", "D1")
        message = str(ctx.exception)
        self.assertIn('display "D1"', message)
        self.assertIn("violates foreign key", message)
        self.assertIn("Nothing was deleted", message)
        self.assertIs(ctx.exception.__cause__, refused)
        self.assertEqual(conn.commits, 0)
        self.assertGreaterEqual(conn.rollbacks, 1)

    def test_uses_the_configured_table_not_the_default(self):
        conn = FakeConn(container_route())
        with patch("db.connection.get_connection", return_value=conn):
            db.delete_container("display", "D1", table="fpl_test")
        texts = [text for text, _ in conn.cur.statements]
        self.assertTrue(any('"fpl_test"' in text for text in texts))
        self.assertFalse(any("filling_product_logs" in text for text in texts))


# ---------------------------------------------------------------------------
# grid delete: rows go, and so do the links they leave empty
# ---------------------------------------------------------------------------

GRID_ROWS = [(1, "U1", 11, "D1", 10, "I1", 5, "C1"),
             (2, "U2", 12, "D1", 10, "I1", 5, "C1")]


def grid_route(*, display_stays=False, inner_stays=True, carton_stays=True):
    """Answers a grid delete of rows 1 and 2, the only units in D1."""
    stays = {"display": display_stays, "inner": inner_stays, "carton": carton_stays}
    parent_link = {"display": [(10, "I1", "inner")], "inner": [(5, "C1", "carton")], "carton": []}

    def route(text, params):
        if text.startswith("SELECT * FROM") and "= ANY(" in text:
            return rows(GRID_ROWS, FLAT_COLUMNS)
        if "unnest(" in text:
            serials, level = params[0], params[1]
            return rows([] if stays[level] else [(serial,) for serial in serials])
        if text.startswith("SELECT id, parent_serial_no") and "= ANY(" in text:
            return rows(parent_link[params[0]])
        if text.startswith(("UPDATE", "DELETE")):
            return count(1)
        return None

    return route


class GridDeleteTests(unittest.TestCase):
    def save(self, route):
        conn = FakeConn(route)
        with patch("db.connection.get_connection", return_value=conn):
            db.save_grid_changes("filling_product_logs", ("id",), [], [(1,), (2,)],
                                 tag_name="OP-1")
        return conn

    def links_deleted(self, conn):
        return [params[0] for text, params in conn.writes()
                if target(text) == "staging_product_logs"]

    def test_deleting_every_row_of_a_display_removes_the_display_link_too(self):
        conn = self.save(grid_route(display_stays=False))
        self.assertEqual(self.links_deleted(conn), [[11, 12], [10]])

    def test_a_display_that_still_holds_other_rows_keeps_its_link(self):
        conn = self.save(grid_route(display_stays=True))
        self.assertEqual(self.links_deleted(conn), [[11, 12]])

    def test_emptying_a_display_can_empty_its_inner_too(self):
        conn = self.save(grid_route(display_stays=False, inner_stays=False))
        self.assertEqual(self.links_deleted(conn), [[11, 12], [5, 10]])

    def test_the_emptiness_check_excludes_the_whole_batch_not_one_row(self):
        # Checked per row, each of the two rows would see the other as a survivor
        # and no link would ever be cleaned up.
        conn = self.save(grid_route(display_stays=False))
        self.assertEqual(
            conn.asked("unnest(")[0],
            (["D1"], "display", [11, 12], [1, 2]),
        )

    def test_unit_links_and_serials_of_deleted_rows_go_as_before(self):
        conn = self.save(grid_route(display_stays=True))
        serials = [p for t, p in conn.writes() if target(t) == "staging_serial_data"]
        self.assertEqual(serials, [("OP-1", ["U1", "U2"])])
        self.assertEqual(self.links_deleted(conn), [[11, 12]])

    def test_rows_without_a_unit_serial_release_nothing(self):
        bare = [(1, None, 11, "D1", 10, "I1", 5, "C1"), (2, "", 12, "D1", 10, "I1", 5, "C1")]
        route = grid_route(display_stays=True)

        def without_serials(text, params):
            if text.startswith("SELECT * FROM") and "= ANY(" in text:
                return rows(bare, FLAT_COLUMNS)
            return route(text, params)

        conn = self.save(without_serials)
        self.assertEqual([t for t, _ in conn.writes() if target(t) == "staging_serial_data"], [])

    def test_a_row_that_already_vanished_does_not_stop_the_rest_of_the_batch(self):
        # Another operator deleted row 2 after this grid loaded. Only row 1 can be read
        # back, yet both pks are still deleted (row 2 harmlessly) and D1 is still judged
        # on what is actually left in the table -- nothing -- so its link goes.
        route = grid_route(display_stays=False)

        def one_row_left(text, params):
            if text.startswith("SELECT * FROM") and "= ANY(" in text:
                return rows(GRID_ROWS[:1], FLAT_COLUMNS)
            return route(text, params)

        conn = self.save(one_row_left)
        self.assertEqual(self.links_deleted(conn), [[11], [10]])
        self.assertEqual(conn.asked("unnest(")[0], (["D1"], "display", [11], [1]))
        self.assertEqual([p for t, p in conn.writes() if target(t) == "flat"], [[1], [2]])
        self.assertEqual((conn.commits, conn.rollbacks), (1, 0))

    def test_the_rows_are_still_deleted_in_the_same_single_transaction(self):
        conn = self.save(grid_route(display_stays=False))
        row_deletes = [p for t, p in conn.writes() if target(t) == "flat"]
        self.assertEqual(row_deletes, [[1], [2]])
        self.assertEqual((conn.commits, conn.rollbacks), (1, 0))
        self.assertEqual(conn.events[-1], ("commit",))


if __name__ == "__main__":
    unittest.main()
