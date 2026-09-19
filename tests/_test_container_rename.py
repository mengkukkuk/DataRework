import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

import psycopg2
from PySide6.QtWidgets import QApplication

import db
import main_window as mw

failures = []


def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        failures.append(label)


# --- the grid refuses to edit a shared container in place --------------------

app = QApplication(sys.argv)
win = mw.MainWindow("tester", "admin")

columns = ["id", "unit_serial_no", "display_serial_no", "display_roll_no", "carton_serial_no"]
rows = [(1, "260800000005", "D_SYNTH_0001", "R_SYNTH_0001", "C_SYNTH_0001")]
win._populate_table(columns, rows, ["id"])
offset = 1 if win._show_delete_col else 0


def cell(col):
    return win.table.item(0, columns.index(col) + offset)


def is_editable(col):
    return bool(cell(col).flags() & mw.Qt.ItemIsEditable)


check("unit_serial_no stays editable (it is 1:1 with the row)", is_editable("unit_serial_no"))
check("display_serial_no is read-only", not is_editable("display_serial_no"))
check("display_roll_no is read-only", not is_editable("display_roll_no"))
check("carton_serial_no is read-only", not is_editable("carton_serial_no"))
check(
    "container cell points the user at the rename action",
    "right-click" in cell("display_serial_no").toolTip().lower(),
)

# --- rename_container against the live DB, rolled back afterwards ------------

real = psycopg2.connect(
    host=os.environ["DB_HOST"],
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
)


class NoCommit:
    """Lets db.* run its own commit() without persisting anything."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        pass

    def rollback(self):
        self._conn.rollback()

    def close(self):
        pass


db.connection.get_connection = lambda: NoCommit(real)
cur = real.cursor()

cur.execute(
    "SELECT parent_serial_no FROM public.staging_product_logs "
    "WHERE parent_serial_label_code = 'display' LIMIT 1"
)
old_display = cur.fetchone()[0]

cur.execute(
    "SELECT count(*) FROM public.staging_product_logs "
    "WHERE parent_serial_no = %s AND parent_serial_label_code = 'display'",
    (old_display,),
)
expected_children = cur.fetchone()[0]

preview = db.container_rename_preview("display", old_display)
check("preview counts the filling rows the container holds", preview["rows"] > 0)
check("preview counts every edge naming the container", preview["edges"] >= expected_children)

NEW_DISPLAY = "D_SYNTH_RENAME_1"
result = db.rename_container("display", old_display, NEW_DISPLAY)

cur.execute(
    "SELECT count(*) FROM public.staging_product_logs "
    "WHERE parent_serial_no = %s AND parent_serial_label_code = 'display'",
    (NEW_DISPLAY,),
)
check("every child edge was re-parented", cur.fetchone()[0] == expected_children)

cur.execute(
    "SELECT count(*) FROM public.staging_product_logs "
    "WHERE serial_no = %s OR parent_serial_no = %s",
    (old_display, old_display),
)
check("no edge still names the old serial", cur.fetchone()[0] == 0)

cur.execute(
    "SELECT count(*) FROM public.filling_product_logs WHERE display_serial_no = %s",
    (NEW_DISPLAY,),
)
check("filling_product_logs agrees with the edge table", cur.fetchone()[0] == result["rows"])

cur.execute(
    "SELECT count(*) FROM public.filling_product_logs WHERE display_serial_no = %s",
    (old_display,),
)
check("no filling row still names the old serial", cur.fetchone()[0] == 0)

real.rollback()

# --- carton: the level that used to silently no-op ---------------------------
# A carton has no carton_source_id column, so the old per-row edge path wrote
# nothing at all and let filling_product_logs drift away from the edge table.

cur.execute(
    "SELECT parent_serial_no FROM public.staging_product_logs "
    "WHERE parent_serial_label_code = 'carton' LIMIT 1"
)
old_carton = cur.fetchone()[0]

cur.execute(
    "SELECT count(*) FROM public.staging_product_logs "
    "WHERE parent_serial_no = %s AND parent_serial_label_code = 'carton'",
    (old_carton,),
)
expected_carton_edges = cur.fetchone()[0]

NEW_CARTON = "C_SYNTH_RENAME_1"
carton_result = db.rename_container("carton", old_carton, NEW_CARTON)

cur.execute(
    "SELECT count(*) FROM public.staging_product_logs "
    "WHERE parent_serial_no = %s AND parent_serial_label_code = 'carton'",
    (NEW_CARTON,),
)
check("carton rename reaches the edge table", cur.fetchone()[0] == expected_carton_edges)

cur.execute(
    "SELECT count(*) FROM public.staging_product_logs WHERE parent_serial_no = %s",
    (old_carton,),
)
check("no edge still names the old carton", cur.fetchone()[0] == 0)

cur.execute(
    "SELECT count(*) FROM public.filling_product_logs WHERE carton_serial_no = %s",
    (old_carton,),
)
check("no filling row still names the old carton", cur.fetchone()[0] == 0)
check("carton rename reports the rows it touched", carton_result["rows"] > 0)

real.rollback()

# --- app-side duplicate protection (no unique constraint exists in the DB) ---

cur.execute(
    "SELECT serial_no, parent_serial_no FROM public.staging_product_logs "
    "WHERE serial_label_code = 'display' LIMIT 1"
)
a_display, its_carton = cur.fetchone()

try:
    db.rename_container("display", a_display, its_carton)
    check("renaming onto a serial already in use is refused", False)
except db.SerialConflictError:
    check("renaming onto a serial already in use is refused", True)
real.rollback()

try:
    db.rename_container("display", "D_SYNTH_DOES_NOT_EXIST", "D_SYNTH_RENAME_2")
    check("renaming a container that does not exist is refused", False)
except db.SerialConflictError:
    check("renaming a container that does not exist is refused", True)
real.rollback()

try:
    db.rename_container("unit", "260800000005", "D_SYNTH_RENAME_3")
    check("unit is rejected as a container level", False)
except ValueError:
    check("unit is rejected as a container level", True)
real.rollback()

try:
    db.rename_container("display", a_display, a_display)
    check("renaming to the same serial is refused", False)
except ValueError:
    check("renaming to the same serial is refused", True)
real.rollback()

# --- stage 1 pickers: levels and their containers ----------------------------

carton_serials = db.container_serials("carton")
check("container_serials lists the cartons", old_carton in carton_serials)
check("container_serials does not repeat a container", len(carton_serials) == len(set(carton_serials)))

try:
    db.container_serials("unit")
    check("container_serials rejects a non-container level", False)
except ValueError:
    check("container_serials rejects a non-container level", True)

# --- stage 2: what the renamed container holds -------------------------------

kids = db.container_children("carton", old_carton)
check("container_children finds the carton's children", len(kids) == expected_carton_edges)
check(
    "each child reports its own level",
    all(k["level"] == "display" for k in kids) if kids else False,
)
check(
    "at least one child reports the units beneath it",
    any(k["children"] > 0 for k in kids),
)
check("an empty container lists nothing", db.container_children("display", "D_SYNTH_NOPE") == [])

# --- stage 2 writes: rename several children at once -------------------------

batch = [("display", kids[0]["serial_no"], "D_SYNTH_CHILD_1"),
         ("display", kids[1]["serial_no"], "D_SYNTH_CHILD_2")]
batch_result = db.rename_children(batch)
check("rename_children reports how many it renamed", batch_result["renamed"] == 2)

cur.execute(
    "SELECT count(*) FROM public.staging_product_logs "
    "WHERE serial_no IN ('D_SYNTH_CHILD_1', 'D_SYNTH_CHILD_2')"
)
check("both children were renamed in one call", cur.fetchone()[0] == 2)

cur.execute(
    "SELECT count(*) FROM public.filling_product_logs "
    "WHERE display_serial_no IN ('D_SYNTH_CHILD_1', 'D_SYNTH_CHILD_2')"
)
check("the batch reached filling_product_logs too", cur.fetchone()[0] == batch_result["rows"])
real.rollback()

check("an empty batch is a no-op, not an error", db.rename_children([])["renamed"] == 0)

try:
    db.rename_children([("display", kids[0]["serial_no"], "D_SYNTH_SAME"),
                        ("display", kids[1]["serial_no"], "D_SYNTH_SAME")])
    check("two children cannot be given the same new serial", False)
except ValueError:
    check("two children cannot be given the same new serial", True)
real.rollback()

try:
    db.rename_children([("display", kids[0]["serial_no"], kids[1]["serial_no"]),
                        ("display", kids[1]["serial_no"], kids[0]["serial_no"])])
    check("a swap is refused rather than half-applied", False)
except ValueError:
    check("a swap is refused rather than half-applied", True)
real.rollback()

# A bad entry anywhere must abort the whole batch, or the operator is left
# guessing which children still carry the old scheme.
try:
    db.rename_children([("display", kids[0]["serial_no"], "D_SYNTH_CHILD_1"),
                        ("display", "D_SYNTH_DOES_NOT_EXIST", "D_SYNTH_CHILD_2")])
    check("a batch with one bad entry is refused", False)
except db.SerialConflictError:
    check("a batch with one bad entry is refused", True)

cur.execute(
    "SELECT count(*) FROM public.staging_product_logs WHERE serial_no = 'D_SYNTH_CHILD_1'"
)
check("the good entry in a refused batch was not applied", cur.fetchone()[0] == 0)
real.rollback()

real.close()

# --- the right-click menu only appears on a container serial -----------------


class StubMenu:
    """Stands in for QMenu so the handler can run without blocking on exec()."""

    offered = []

    def __init__(self, parent=None):
        pass

    def addAction(self, text):
        StubMenu.offered.append(text)
        return object()

    def exec(self, _global_pos):
        return None  # user dismissed the menu


mw.QMenu = StubMenu


def right_click(col):
    StubMenu.offered = []
    item = cell(col)
    win._on_table_context_menu(win.table.visualItemRect(item).center())
    return StubMenu.offered


check(
    "right-clicking a display serial offers a rename action",
    any("display" in text for text in right_click("display_serial_no")),
)
check(
    "right-clicking a carton serial offers a rename action",
    any("carton" in text for text in right_click("carton_serial_no")),
)
check("right-clicking a unit serial offers nothing", right_click("unit_serial_no") == [])
check("right-clicking a plain column offers nothing", right_click("id") == [])


# --- the two-stage dialogs ---------------------------------------------------

import rename_dialog as rd

check(
    "a child named after its parent follows the parent's rename",
    rd.suggest_child_serial("C26080000001-D03", "C26080000001", "C26080000009")
    == "C26080000009-D03",
)
check(
    "a child named independently keeps its serial until the user types one",
    rd.suggest_child_serial("D_SYNTH_0001", "C_SYNTH_0001", "C_SYNTH_0009") == "D_SYNTH_0001",
)

synthetic_children = [
    {"serial_no": "D_SYNTH_0001", "level": "display", "children": 6},
    {"serial_no": "D_SYNTH_0002", "level": "display", "children": 0},
]
panel = mw.ChildRelabelDialog(win, "carton", "C_SYNTH_0001", "C_SYNTH_0009", synthetic_children)

check("every child starts ticked", len(panel._rows) == 2 and all(c.isChecked() for c, _, _ in panel._rows))
check(
    "a child whose serial is unchanged is not submitted as a rename",
    panel.renames() == [],
)

panel._rows[0][2].setText("D_SYNTH_0009")
check(
    "editing one child submits only that child",
    panel.renames() == [("display", "D_SYNTH_0001", "D_SYNTH_0009")],
)

panel._rows[0][0].setChecked(False)
check("unticking a child drops it from the batch", panel.renames() == [])
check("an unticked child's field is locked", not panel._rows[0][2].isEnabled())

panel._set_all(True)
panel._rows[1][2].setText("D_SYNTH_0009")
check("two children sharing a new serial blocks Apply", not panel.apply_btn.isEnabled())
panel._rows[1][2].setText("D_SYNTH_0010")
check("fixing the clash re-enables Apply", panel.apply_btn.isEnabled())
check("Apply names the number of changes", "2" in panel.apply_btn.text())


class ExplodingDialog:
    """Any construction means the pending-edit guard failed to stop the rename."""

    def __init__(self, *_args, **_kwargs):
        raise AssertionError("opened the rename dialog despite pending edits")


mw.RenameContainerDialog = ExplodingDialog

cell("unit_serial_no").setText("260800000099")
win._rename_container("display", "D_SYNTH_0001")
check(
    "pending cell edits block a rename instead of being silently discarded",
    "pending edits" in win.status_label.text().lower(),
)

print()
if failures:
    print(f"{len(failures)} check(s) FAILED: {failures}")
    sys.exit(1)
else:
    print("All checks passed.")
