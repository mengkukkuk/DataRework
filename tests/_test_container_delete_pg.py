"""Run the container-delete SQL against a real PostgreSQL, on TEMP tables only.

Not part of test discovery (leading underscore). test_container_delete.py drives the
code with a hand-written cursor, so it cannot show that the SQL is valid or selects
the right rows; this can.

    .venv\\Scripts\\python.exe tests\\_test_container_delete_pg.py

Connects with the DB_* settings in .env, or with DATAREWORK_TEST_DSN when set (for
example a throwaway local cluster). Everything happens in TEMP tables of one session
(schema pg_temp) and is rolled back at the end. Every statement is checked before it
runs and the script stops if one mentions `public`, so no real table can be touched.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import psycopg2
from psycopg2 import sql

dsn = os.environ.get("DATAREWORK_TEST_DSN")
if dsn:
    real = psycopg2.connect(dsn)
else:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    real = psycopg2.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )

import db  # noqa: E402  (after .env so its defaults are not read from a bare environment)

failures = []


def check(label, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


# --- keep every db.* statement away from real tables -------------------------------

class GuardedCursor:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._cur.close()
        return False

    def execute(self, query, params=None):
        text = query.as_string(real) if isinstance(query, sql.Composable) else query
        if "public" in text.lower():
            raise SystemExit(f"refusing to run a statement that mentions public: {text[:160]}")
        return self._cur.execute(query, params)

    def __getattr__(self, name):
        return getattr(self._cur, name)


class Session:
    """What db.* sees as a connection: commit does nothing, and rollback returns to how
    things stood when this db.* call began (so a scenario's own setup survives it)."""

    def __init__(self):
        with real.cursor() as cur:
            cur.execute("SAVEPOINT attempt")

    def cursor(self):
        return GuardedCursor(real.cursor())

    def commit(self):
        pass

    def rollback(self):
        with real.cursor() as cur:
            cur.execute("ROLLBACK TO SAVEPOINT attempt")

    def close(self):
        pass


db.connection.get_connection = lambda: Session()
raw = real.cursor()


def scalar(text, *params):
    raw.execute(text, params)
    return raw.fetchone()[0]


# --- fixture: two cartons, three inners, four displays -----------------------------
#
#   C1 > I1 > D1 (6 units), D2 (6 units)        C2 > I3 > D4 (2 units)
#        I2 > D3 (6 units)
# Unit serials in the inventory carry a trailing space, as staging_serial_data does.

raw.execute("""CREATE TEMP TABLE staging_product_logs (
    id serial PRIMARY KEY, serial_no varchar(64) NOT NULL, serial_label_code varchar(16) NOT NULL,
    parent_serial_no varchar(64), parent_serial_label_code varchar(16),
    source_roll_no varchar(64), target_roll_no varchar(64))""")
raw.execute("""CREATE TEMP TABLE filling_product_logs (
    id serial PRIMARY KEY, assignment_no varchar(64), product_name varchar(128),
    created_at timestamp DEFAULT now(),
    unit_serial_no varchar(64), unit_roll_no varchar(64), unit_source_id integer,
    display_serial_no varchar(64), display_roll_no varchar(64), display_source_id integer,
    display_target_id integer,
    inner_serial_no varchar(64), inner_roll_no varchar(64), inner_source_id integer,
    inner_target_id integer,
    carton_serial_no varchar(64), carton_roll_no varchar(64), carton_target_id integer)""")
raw.execute("""CREATE TEMP TABLE staging_serial_data (
    id serial PRIMARY KEY, serial_no varchar(64), roll_no varchar(64),
    activate boolean, activate_by varchar(64))""")


def link(child, child_label, parent, parent_label):
    raw.execute(
        "INSERT INTO pg_temp.staging_product_logs "
        "(serial_no, serial_label_code, parent_serial_no, parent_serial_label_code) "
        "VALUES (%s, %s, %s, %s) RETURNING id", (child, child_label, parent, parent_label))
    return raw.fetchone()[0]


def make_display(carton, inner, inner_link, display, units):
    display_link = link(display, "display", inner, "inner")
    for n in range(1, units + 1):
        serial = f"{display}U{n}"
        unit_link = link(serial, "unit", display, "display")
        raw.execute(
            "INSERT INTO pg_temp.filling_product_logs (assignment_no, product_name, unit_serial_no, "
            "unit_source_id, display_serial_no, display_source_id, inner_serial_no, inner_source_id, "
            "carton_serial_no) VALUES ('JOB', 'PRODUCT', %s, %s, %s, %s, %s, %s, %s)",
            (serial, unit_link, display, display_link, inner, inner_link, carton))
        raw.execute("INSERT INTO pg_temp.staging_serial_data (serial_no, roll_no, activate, activate_by) "
                    "VALUES (%s, 'R1', true, 'seed')", (serial + " ",))


for carton, inners in {"C1": {"I1": ["D1", "D2"], "I2": ["D3"]}, "C2": {"I3": ["D4"]}}.items():
    for inner, displays in inners.items():
        inner_link = link(inner, "inner", carton, "carton")
        for display in displays:
            make_display(carton, inner, inner_link, display, 2 if display == "D4" else 6)

raw.execute("SAVEPOINT fixture")


def counts():
    return {
        "edges": scalar("SELECT count(*) FROM pg_temp.staging_product_logs"),
        "rows": scalar("SELECT count(*) FROM pg_temp.filling_product_logs"),
        "active": scalar("SELECT count(*) FROM pg_temp.staging_serial_data WHERE activate"),
    }


BASELINE = counts()
check("fixture is what the scenarios assume", BASELINE == {"edges": 27, "rows": 20, "active": 20})


def back_to_fixture():
    raw.execute("ROLLBACK TO SAVEPOINT fixture")


def named(serial, level):
    return scalar("SELECT count(*) FROM pg_temp.staging_product_logs "
                  "WHERE (serial_no = %s AND serial_label_code = %s) "
                  "OR (parent_serial_no = %s AND parent_serial_label_code = %s)",
                  serial, level, serial, level)


def linked(child, child_label, parent):
    return scalar("SELECT count(*) FROM pg_temp.staging_product_logs "
                  "WHERE serial_no = %s AND serial_label_code = %s AND parent_serial_no = %s",
                  child, child_label, parent) == 1


def in_rows(level, serial):
    return scalar(f"SELECT count(*) FROM pg_temp.filling_product_logs WHERE {level}_serial_no = %s",
                  serial)


S = {"schema": "pg_temp"}

# --- preview writes nothing and counts the right things ----------------------------

preview = db.container_delete_preview("display", "D1", **S)
check("preview D1: 6 rows, 6 units", (preview["rows"], preview["units"]) == (6, 6))
check("preview D1: its own link + 6 unit links; I1 keeps D2 so I1 is not emptied",
      preview["edges"] == 7 and preview["emptied"] == [])
check("preview D1 lists the six units in order",
      [c["serial_no"] for c in preview["children"]] == [f"D1U{n}" for n in range(1, 7)])
check("preview wrote nothing", counts() == BASELINE)

# --- delete one display; its siblings and parents are untouched --------------------

result = db.delete_container("display", "D1", tag_name="OP-9", expected=preview, **S)
check("delete D1 reports what the preview promised",
      result == {"rows": 6, "edges": 7, "units": 6, "emptied": [], "orphans": 0})
check("D1 is gone from rows and links", in_rows("display", "D1") == 0 and named("D1", "display") == 0)
check("sibling D2 keeps its rows and links", in_rows("display", "D2") == 6 and named("D2", "display") == 7)
check("I1 -> C1 link survives", linked("I1", "inner", "C1"))
check("D1's units were released with the operator tag, despite the trailing space in the inventory",
      scalar("SELECT count(*) FROM pg_temp.staging_serial_data "
             "WHERE btrim(serial_no) LIKE 'D1U%%' AND NOT activate AND activate_by = 'OP-9'") == 6)
check("nobody else was released", counts()["active"] == BASELINE["active"] - 6)
back_to_fixture()

# --- a parent left empty goes with its last child ----------------------------------

db.delete_container("display", "D1", **S)
second = db.delete_container("display", "D2", **S)
check("deleting D2 after D1 empties I1, which is reported and removed",
      second["emptied"] == [{"level": "inner", "serial_no": "I1"}])
check("I1 is gone, C1 still holds I2", named("I1", "inner") == 0 and named("I2", "inner") == 2)
back_to_fixture()

# --- deleting a parent takes everything below it -----------------------------------

inner = db.delete_container("inner", "I1", **S)
check("delete inner I1: 12 rows, 12 units, 15 links (2 displays, 12 units, its own)",
      (inner["rows"], inner["units"], inner["edges"]) == (12, 12, 15))
check("nothing of I1 is left; I2 and the other carton are intact",
      named("I1", "inner") == 0 and in_rows("inner", "I1") == 0
      and in_rows("inner", "I2") == 6 and in_rows("carton", "C2") == 2)
back_to_fixture()

carton = db.delete_container("carton", "C1", **S)
check("delete carton C1: 18 rows and 23 links (2 inners, 3 displays, 18 units)",
      (carton["rows"], carton["edges"]) == (18, 23))
check("only C2 remains", counts() == {"edges": 4, "rows": 2, "active": 2})
back_to_fixture()

# --- grid delete: rows go, and links only when a container is left empty -----------

d1_rows = [(pk,) for (pk,) in (raw.execute("SELECT id FROM pg_temp.filling_product_logs "
                                           "WHERE display_serial_no = 'D1' ORDER BY id") or raw.fetchall())]
db.save_grid_changes("filling_product_logs", ("id",), [], d1_rows[:1], tag_name="OP-9", **S)
check("grid delete of one of D1's rows keeps D1's link",
      named("D1", "display") == 6 and in_rows("display", "D1") == 5)
back_to_fixture()

db.save_grid_changes("filling_product_logs", ("id",), [], d1_rows, tag_name="OP-9", **S)
check("grid delete of all six rows removes D1's link too (no orphan), and only D1's",
      named("D1", "display") == 0 and named("D2", "display") == 7 and linked("I1", "inner", "C1"))
check("and released their serials", counts()["active"] == BASELINE["active"] - 6)
back_to_fixture()

d1_d2 = [(pk,) for (pk,) in (raw.execute("SELECT id FROM pg_temp.filling_product_logs "
                                         "WHERE display_serial_no IN ('D1','D2') ORDER BY id")
                             or raw.fetchall())]
db.save_grid_changes("filling_product_logs", ("id",), [], d1_d2, **S)
check("grid delete emptying D1 and D2 removes both display links and then I1's link",
      named("D1", "display") == 0 and named("D2", "display") == 0 and named("I1", "inner") == 0)
check("C1 still holds I2, so nothing above I1 goes", named("I2", "inner") == 2 and in_rows("carton", "C1") == 6)
back_to_fixture()

# --- a row somebody else already deleted must not keep its container alive ----------

d4 = [pk for (pk,) in (raw.execute("SELECT id FROM pg_temp.filling_product_logs "
                                   "WHERE display_serial_no = 'D4' ORDER BY id") or raw.fetchall())]
vanished, last = d4
raw.execute("DELETE FROM pg_temp.staging_product_logs WHERE id = "
            "(SELECT unit_source_id FROM pg_temp.filling_product_logs WHERE id = %s)", (vanished,))
raw.execute("DELETE FROM pg_temp.filling_product_logs WHERE id = %s", (vanished,))
db.save_grid_changes("filling_product_logs", ("id",), [], [(vanished,), (last,)], **S)
check("the last row of D4 goes, its pk list including one that was already gone, and D4 and I3 "
      "are cleaned up (the survivor check reads the live table)",
      in_rows("display", "D4") == 0 and named("D4", "display") == 0 and named("I3", "inner") == 0)
back_to_fixture()

# --- a row pointing at a link that is already gone must not block the delete -------

raw.execute("UPDATE pg_temp.filling_product_logs SET unit_source_id = 999999 "
            "WHERE display_serial_no = 'D1' AND unit_serial_no = 'D1U1'")
orphaned = db.container_delete_preview("display", "D1", **S)
check("the preview counts out the link that no longer exists (the six real unit "
      "links and D1's own are still there)",
      (orphaned["edges"], orphaned["orphans"]) == (7, 1))
result = db.delete_container("display", "D1", expected=orphaned, **S)
check("and the delete goes through, leaving nothing of D1",
      result["orphans"] == 1 and in_rows("display", "D1") == 0 and named("D1", "display") == 0)
check("the link the row wrongly named is not counted as deleted", result["edges"] == 7)
back_to_fixture()

# --- refusals leave everything as it was ------------------------------------------

link("D1", "display", "I9", "inner")
try:
    db.container_delete_preview("display", "D1", **S)
    refused = False
except db.ContainerDeleteError as exc:
    refused = "more than one" in str(exc)
check("a serial linked under two parents is refused", refused)
back_to_fixture()

stale = db.container_delete_preview("display", "D1", **S)
link("D1U7", "unit", "D1", "display")  # somebody adds a child after the user looked
try:
    db.delete_container("display", "D1", expected=stale, **S)
    refused = False
except db.ContainerDeleteError as exc:
    refused = "changed" in str(exc)
check("a container that changed since the preview is refused", refused)
check("and nothing was deleted", in_rows("display", "D1") == 6 and named("D1", "display") == 8)
back_to_fixture()

# --- links with no saved row, loops, and rows with no links -------------------------

link("D1U7", "unit", "D1", "display")
raw.execute("INSERT INTO pg_temp.staging_serial_data (serial_no, activate, activate_by) "
            "VALUES ('D1U7 ', true, 'seed')")
edge_only = db.container_delete_preview("display", "D1", **S)
check("a unit that has a link but no saved row is counted", (edge_only["units"], edge_only["edges"]) == (7, 8))
db.delete_container("display", "D1", tag_name="OP-9", expected=edge_only, **S)
check("and its link is deleted and its serial released",
      named("D1U7", "unit") == 0
      and scalar("SELECT NOT activate FROM pg_temp.staging_serial_data WHERE btrim(serial_no) = 'D1U7'"))
back_to_fixture()

link("L1", "display", "I1", "inner")
link("L1", "display", "L2", "display")
link("L2", "display", "L1", "display")
looped = db.container_delete_preview("inner", "I1", **S)
listed = [c["serial_no"] for c in looped["children"]]
check("a loop in the links terminates and lists each item once",
      listed.count("L1") == 1 and listed.count("L2") == 1)
back_to_fixture()

raw.execute("INSERT INTO pg_temp.filling_product_logs (unit_serial_no, display_serial_no) "
            "VALUES ('D7U1', 'D7'), ('D7U2', 'D7')")
bare = db.container_delete_preview("display", "D7", **S)
check("rows that have no links at all can be previewed (empty id lists are accepted)",
      (bare["rows"], bare["edges"], bare["units"]) == (2, 0, 2))
db.delete_container("display", "D7", expected=bare, **S)
check("and deleted", in_rows("display", "D7") == 0)
back_to_fixture()

# --- releasing serials keeps the operator when no tag is given ----------------------

db.delete_container("display", "D2", **S)
check("with no operator tag the existing activate_by is kept",
      scalar("SELECT count(*) FROM pg_temp.staging_serial_data "
             "WHERE btrim(serial_no) LIKE 'D2U%%' AND NOT activate AND activate_by = 'seed'") == 6)
back_to_fixture()

real.rollback()
real.close()
print()
print("FAILED: " + ", ".join(failures) if failures else "all checks passed (nothing was committed)")
sys.exit(1 if failures else 0)
