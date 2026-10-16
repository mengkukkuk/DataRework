"""Renaming onto a serial that is damaged or already in use, against a real PostgreSQL.

Not part of test discovery (leading underscore). The mocked tests cannot show what the
database ends up holding, which is what the GUI reloads after a rename:

    .venv\\Scripts\\python.exe tests\\_test_serial_guard_pg.py

Rule under test: staging_serial_data rows with is_damaged or is_use true are never
updated, and the rename that would have activated them is refused whole -- the grid
must not show a serial the inventory never took.

Connects with the DB_* settings in .env, or DATAREWORK_TEST_DSN. Everything happens in
TEMP tables of one session (schema pg_temp). Every statement is checked before it runs
and the script stops if one mentions `public`, so no real table can be touched. Run for
is_use as boolean and as varchar, since the column's real type is not known.
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

import db  # noqa: E402

failures = []


def check(label, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


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
    """A connection whose commit is a no-op, but which, like a real one, throws away
    everything written if it is closed without commit() having been called."""

    def __init__(self):
        self.committed = False
        with real.cursor() as cur:
            cur.execute("SAVEPOINT attempt")

    def cursor(self):
        return GuardedCursor(real.cursor())

    def commit(self):
        self.committed = True

    def rollback(self):
        with real.cursor() as cur:
            cur.execute("ROLLBACK TO SAVEPOINT attempt")

    def close(self):
        if not self.committed:
            self.rollback()


db.connection.get_connection = lambda: Session()
raw = real.cursor()


def scalar(text, *params):
    raw.execute(text, params)
    return raw.fetchone()[0]


S = {"schema": "pg_temp"}


def run(is_use_type):
    print(f"\n=== is_use as {is_use_type} ===")

    def flag(value):
        return value if is_use_type == "boolean" else str(value).lower()

    raw.execute("""CREATE TEMP TABLE staging_product_logs (
        id serial PRIMARY KEY, serial_no varchar(64) NOT NULL, serial_label_code varchar(16) NOT NULL,
        parent_serial_no varchar(64), parent_serial_label_code varchar(16),
        source_roll_no varchar(64), target_roll_no varchar(64))""")
    raw.execute("""CREATE TEMP TABLE filling_product_logs (
        id serial PRIMARY KEY, assignment_no varchar(64), product_name varchar(128),
        unit_serial_no varchar(64), unit_roll_no varchar(64), unit_source_id integer,
        display_serial_no varchar(64), display_roll_no varchar(64), display_source_id integer,
        inner_serial_no varchar(64), inner_roll_no varchar(64), inner_source_id integer,
        carton_serial_no varchar(64), carton_roll_no varchar(64))""")
    raw.execute(f"""CREATE TEMP TABLE staging_serial_data (
        id serial PRIMARY KEY, serial_no varchar(64), roll_no varchar(64),
        activate boolean, is_use {is_use_type}, is_damaged boolean, activate_by varchar(64))""")

    def link(child, label, parent, parent_label):
        raw.execute("INSERT INTO pg_temp.staging_product_logs (serial_no, serial_label_code, "
                    "parent_serial_no, parent_serial_label_code) VALUES (%s,%s,%s,%s) RETURNING id",
                    (child, label, parent, parent_label))
        return raw.fetchone()[0]

    def inventory(serial, activate, is_use, damaged=False):
        # trailing space, as staging_serial_data really stores it
        raw.execute("INSERT INTO pg_temp.staging_serial_data (serial_no, roll_no, activate, is_use, "
                    "is_damaged, activate_by) VALUES (%s,'R1',%s,%s,%s,'seed')",
                    (serial + " ", activate, flag(is_use), damaged))

    # C1 > I1 > D1 > D1U1, D1U2
    inner_link = link("I1", "inner", "C1", "carton")
    display_link = link("D1", "display", "I1", "inner")
    for n in (1, 2):
        unit = f"D1U{n}"
        unit_link = link(unit, "unit", "D1", "display")
        raw.execute("INSERT INTO pg_temp.filling_product_logs (assignment_no, product_name, "
                    "unit_serial_no, unit_source_id, display_serial_no, display_source_id, "
                    "inner_serial_no, inner_source_id, carton_serial_no) "
                    "VALUES ('JOB','P',%s,%s,'D1',%s,'I1',%s,'C1')",
                    (unit, unit_link, display_link, inner_link))
        inventory(unit, True, True)
    for serial in ("D1", "I1", "C1"):
        inventory(serial, True, True)

    # What a rename can land on
    inventory("U-FREE", False, False)               # clean
    inventory("U-USED", True, True)                 # already in use
    inventory("U-FLAG", False, True)                # is_use true while activate is false
    inventory("U-DMG", False, False, damaged=True)  # damaged
    inventory("D-FREE", False, False)
    inventory("D-USED", True, True)
    inventory("D-DMG", False, False, damaged=True)
    raw.execute("SAVEPOINT fixture")

    def back():
        raw.execute("ROLLBACK TO SAVEPOINT fixture")

    def inv(serial):
        raw.execute("SELECT activate, is_use::text, is_damaged, activate_by "
                    "FROM pg_temp.staging_serial_data WHERE btrim(serial_no) = %s", (serial,))
        row = raw.fetchone()
        return (row[0], row[1] in ("true", "t"), row[2], row[3])

    def named(serial):
        return scalar("SELECT (SELECT count(*) FROM pg_temp.staging_product_logs "
                      "WHERE serial_no = %s OR parent_serial_no = %s) + "
                      "(SELECT count(*) FROM pg_temp.filling_product_logs "
                      "WHERE unit_serial_no = %s OR display_serial_no = %s)",
                      serial, serial, serial, serial)

    def refused(call):
        try:
            call()
        except db.SerialInventoryError as exc:
            return str(exc)
        except Exception as exc:                                   # noqa: BLE001
            return f"WRONG EXCEPTION {type(exc).__name__}: {exc}"
        return None

    # --- sanity: a clean target still renames and flips the flags --------------------
    result = db.rename_container("unit", "D1U1", "U-FREE", **S)
    check("clean unit rename succeeds", result["rows"] == 1)
    check("clean target is now active and in use", inv("U-FREE")[:2] == (True, True))
    check("the old unit was released", inv("D1U1")[:2] == (False, False))
    check("rows and links carry the new serial", named("U-FREE") == 2 and named("D1U1") == 0)
    back()

    # --- unit rename onto a blocked serial ------------------------------------------
    for target, why in (("U-USED", "already in use"), ("U-FLAG", "is_use true"),
                        ("U-DMG", "damaged")):
        before = inv(target)
        message = refused(lambda t=target: db.rename_container("unit", "D1U1", t, **S))
        check(f"unit rename onto a {why} serial is refused", message is not None
              and not message.startswith("WRONG"))
        check(f"  ...and says which serial: {message!r}"[:90], message is not None and target in message)
        check(f"  ...the {why} inventory row is untouched", inv(target) == before)
        check("  ...the old unit is still active and still in the rows and links",
              inv("D1U1")[:2] == (True, True) and named("D1U1") == 2 and named(target) == 0)
        back()

    # --- container rename ------------------------------------------------------------
    for target, why in (("D-USED", "already in use"), ("D-DMG", "damaged")):
        before = inv(target)
        message = refused(lambda t=target: db.rename_container("display", "D1", t, **S))
        check(f"display rename onto a {why} serial is refused", message is not None
              and not message.startswith("WRONG"))
        check(f"  ...nothing was renamed and the row is untouched",
              named("D1") == 1 + 2 + 2 and named(target) == 0 and inv(target) == before)
        back()
    result = db.rename_container("display", "D1", "D-FREE", **S)
    check("clean display rename still works", inv("D-FREE")[:2] == (True, True)
          and inv("D1")[:2] == (False, False) and named("D1") == 0)
    back()

    # --- second panel: the batch is all or nothing ----------------------------------
    message = refused(lambda: db.rename_children(
        [("unit", "D1U1", "U-FREE"), ("unit", "D1U2", "U-DMG")], **S))
    check("a child batch with one blocked serial is refused", message is not None
          and not message.startswith("WRONG"))
    check("  ...including the clean rename in the same batch",
          named("U-FREE") == 0 and named("D1U1") == 2 and inv("U-FREE")[:2] == (False, False))
    back()
    db.rename_children([("unit", "D1U1", "U-FREE")], **S)
    check("a clean child batch still works", named("U-FREE") == 2 and inv("U-FREE")[:2] == (True, True))
    back()

    # --- grid save: editing a unit serial in the cell -------------------------------
    pk = scalar("SELECT id FROM pg_temp.filling_product_logs WHERE unit_serial_no = 'D1U1'")
    for target, why in (("U-USED", "already in use"), ("U-DMG", "damaged")):
        before = inv(target)
        message = refused(lambda t=target: db.save_grid_changes(
            "filling_product_logs", ("id",), [((pk,), {"unit_serial_no": t})], [],
            tag_name="OP-1", **S))
        check(f"grid save onto a {why} serial is refused", message is not None
              and not message.startswith("WRONG"))
        check("  ...the cell, the links and the inventory are all untouched",
              named(target) == 0 and named("D1U1") == 2 and inv(target) == before
              and inv("D1U1")[:2] == (True, True))
        back()
    db.save_grid_changes("filling_product_logs", ("id",), [((pk,), {"unit_serial_no": "U-FREE"})], [],
                         tag_name="OP-1", **S)
    check("grid save onto a clean serial still works",
          named("U-FREE") == 2 and inv("U-FREE") == (True, True, False, "OP-1")
          and inv("D1U1")[:2] == (False, False))

    for name in ("staging_serial_data", "filling_product_logs", "staging_product_logs"):
        raw.execute(f"DROP TABLE pg_temp.{name}")


try:
    run("boolean")
    run("varchar(8)")
finally:
    real.rollback()
    real.close()

print()
if failures:
    print(f"{len(failures)} FAILED")
    sys.exit(1)
print("all passed")
