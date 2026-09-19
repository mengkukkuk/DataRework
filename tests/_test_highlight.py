import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from PySide6.QtWidgets import QApplication

import main_window as mw

app = QApplication(sys.argv)

win = mw.MainWindow("tester", "admin")

columns = ["id", "unit_serial_no", "product_name"]
rows = [
    (1, "260800000007", "Matte Poreless"),
    (2, "260800000008", "Matte Poreless"),
]
pk_columns = ["id"]
win._populate_table(columns, rows, pk_columns)

offset = 1 if win._show_delete_col else 0
del_item = win.table.item(0, 0)
serial_item = win.table.item(0, 1 + offset)
name_item = win.table.item(0, 2 + offset)

failures = []

def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        failures.append(label)

# Check the Del checkbox for row 0 -> whole row should glow red
del_item.setCheckState(mw.Qt.Checked)
check("serial cell turns red when row marked for delete", serial_item.background().color() == mw.DELETED_ROW_BG)
check("product_name cell turns red when row marked for delete", name_item.background().color() == mw.DELETED_ROW_BG)

# Edits on a deleted row should stay red, not flip green
serial_item.setText("CHANGED_BUT_DELETED")
check("editing a deleted row's cell stays red (not green)", serial_item.background().color() == mw.DELETED_ROW_BG)

# Row 1 (not checked) must be unaffected
other_item = win.table.item(1, 1 + offset)
check("row 1 unaffected by row 0's delete mark", other_item.background().style() == mw.Qt.NoBrush)

# Uncheck -> row returns to normal; the edited cell should now show green
# (since its text still differs from original), the untouched cell should be clear
del_item.setCheckState(mw.Qt.Unchecked)
check("unchecked row: previously-edited cell reverts to green", serial_item.background().color() == mw.EDITED_CELL_BG)
check("unchecked row: untouched cell has no highlight", name_item.background().style() == mw.Qt.NoBrush)

print()
if failures:
    print(f"{len(failures)} check(s) FAILED: {failures}")
    sys.exit(1)
else:
    print("All checks passed.")
