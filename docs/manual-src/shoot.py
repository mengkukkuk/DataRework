"""Render the manual's screenshots from FAKE data into docs/manual-src/shots/.

Run with the project venv:  .venv\Scripts\python.exe docs\manual-src\shoot.py
Never touches a database (get_connection is replaced by a function that raises)
and never writes the registry (QSettings and the language choice stay in memory).
Windows fonts are loaded by hand because Qt's offscreen platform has none.
"""
import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DB_HOST"] = "127.0.0.1"
os.environ["DAMAGE_REPORT_DIR"] = r"C:\Reports"  # keep the real user folder out of the shots
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "shots")
sys.path.insert(0, ROOT); os.chdir(ROOT)

from unittest.mock import patch
import datetime
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

app = QApplication([])
from PySide6.QtGui import QFontDatabase
for f in ("LeelawUI.ttf","leelawdb.ttf","segoeui.ttf","segoeuib.ttf","seguisym.ttf","tahoma.ttf","tahomabd.ttf",
          "SegoeIcons.ttf","segmdl2.ttf"):  # gear and undo/redo glyphs
    print(f, QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\\"+f))

import db, db.connection, db_worker
def _no_db(*a, **k): raise RuntimeError("database access is disabled in the screenshot harness")
db.connection.get_connection = _no_db
db.get_connection = _no_db

# fake data ---------------------------------------------------------------
PRODUCT = "Matte Poreless รองพื้น _01 Silky Ivory"
COLS = ["id", "assignment_no", "product_name", "created_at",
        "unit_serial_no", "unit_roll_no", "display_serial_no", "display_roll_no",
        "inner_serial_no", "carton_serial_no"]
rows, groups, n = [], [], 0
for c in (1, 2):
    for i in (1, 2):
        for d in (1, 2, 3):
            for u in (1, 2, 3, 4):
                n += 1
                carton, inner = f"C260800{c:03d}", f"I260800{c}{i}"
                disp, unit = f"D260800{c}{i}{d}", f"U26080{n:05d}"
                rows.append((n, "AJ-26-0042", PRODUCT, datetime.datetime(2026, 10, 7, 9, n % 60),
                             unit, "R1001", disp, "R2001", inner, carton))
                groups.append((carton, inner, disp, unit, 1, [PRODUCT]))
rows = rows[:24]

tmp = tempfile.mkdtemp()
def fake_settings():
    return QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat)

patches = [
    patch("db.get_columns", return_value=COLS),
    patch("db.get_primary_key_columns", return_value=["id"]),
    patch("db.query_rows", return_value=(COLS, rows)),
    patch("db.fetch_distinct_values", side_effect=lambda t, col, **k: {
        "assignment_no": ["AJ-26-0042", "AJ-26-0041"], "product_name": [PRODUCT, "Lip Tint 02 Rose"],
    }.get(col, [r[COLS.index(col)] for r in rows[:8]] if col in COLS else [])),
    patch("db.container_groups", return_value=groups),
    patch("db.container_serials", side_effect=lambda lvl, *a, **k: sorted({g[("carton","inner","display","unit").index(lvl)] for g in groups})[:12]),
    patch("db.container_rename_preview", return_value={"rows": 12, "edges": 15}),
    patch("db.container_delete_preview", return_value={
        "level": "inner", "serial_no": "I26080011", "rows": 12, "edges": 15, "units": 12, "emptied": [],
        "children": [{"serial_no": f"D26080011{k}", "level": "display", "depth": 1, "children": 4} for k in (1,2,3)]
        + [{"serial_no": f"U2608{k:05d}", "level": "unit", "depth": 2, "children": 0} for k in range(1, 5)]}),
    patch("db.container_children", return_value=[
        {"serial_no": f"D26080011{k}", "level": "display", "children": 4} for k in (1,2,3)]),
    patch("db.serial_level", return_value="unit"),
    patch("main_window._get_settings", fake_settings),
]
for p in patches: p.start()

def run_sync(fn, *args, on_success=None, on_error=None, request_id=None, **kwargs):
    try: result = fn(*args, **kwargs)
    except Exception as exc:
        if on_error: on_error(exc, request_id)
        return
    if on_success: on_success(result, request_id)
db_worker.run_async = run_sync

import i18n
from i18n import language
import main_window as mw
from main_window import MainWindow
from login_window import LoginWindow
from rename_dialog import RenameContainerDialog, ChildRelabelDialog
from delete_dialog import DeleteContainerDialog
from debug_log import LOG, LogWindow
import theme

def pump():
    for _ in range(5): app.processEvents()

def grab(w, name, lang):
    pump(); w.grab().save(os.path.join(OUT, f"{name}_{lang}.png"))

def shoot(lang):
    language.code = lang  # in memory only: never persisted to the registry
    app.setFont(__import__("typography").ui_font())
    # login
    lw = LoginWindow(); lw.setStyleSheet(theme._render_stylesheet("light", "login.css")); lw.resize(520, 690)
    lw.username_input.setText("operator01"); lw.show(); grab(lw, "login", lang); lw.close()

    win = MainWindow("operator01", "admin", "OP01")
    win._set_theme("light"); win.resize(1300, 760); win.show()
    # records
    win.job_combo.setCurrentText("AJ-26-0042")
    win._on_search(); win._show_status(i18n.tr("{p0} row(s) loaded.", p0=24)); pump()
    grab(win, "records", lang)
    # edits: one edited cell + one marked row
    win.table.item(1, 5).setText("U2608999901")
    win.table.item(3, 0).setCheckState(Qt.Checked)
    grab(win, "records_edit", lang)
    win._on_search(); win.table.clearSelection()
    # folded filters
    win._toggle_filters(); win._filter_summary(); grab(win, "filters_folded", lang); win._toggle_filters()
    # scope bar
    win._set_record_scope(("C260800001", "I26080011", "D260800111"))
    grab(win, "records_scope", lang); win._set_record_scope(None)
    # container manager
    win.views.setCurrentIndex(1); win._refresh_containers(); win.container_panel._stop_animation(); pump()
    grab(win, "containers", lang)
    cp = win.container_panel
    for key, path in (("containers_deep", ("C260800001", "I26080011")),
                      ("containers_units", ("C260800001", "I26080011", "D260800111"))):
        cp.navigate(path); cp._stop_animation(); grab(win, key, lang)
    # damage
    win.views.setCurrentIndex(2); win.damage_panel.serial_edit.setText("U2608012345"); grab(win, "damage", lang)
    win.damage_panel._set_result('Reported "U2608012345" damaged.')
    # export: range unticked, with a finished export's message
    dp = win.damage_panel
    dp.serial_edit.clear(); dp.any_time_check.setChecked(False)
    dp._set_result(i18n.tr('Reported "{p0}" damaged.', p0="U2608012345"))
    dp._set_result(i18n.tr("Exported {p0} damaged serial(s) to {p1}", p0=4, p1=r"C:\Reports\damage_report_20261019_145512.pdf"),
                   label=dp.export_result_label)
    grab(win, "damage_export", lang)
    win.views.setCurrentIndex(0)
    # read-only role
    ro = MainWindow("viewer01", "user", "VW01"); ro._set_theme("light"); ro.resize(1300, 760); ro.show()
    ro._on_search(); ro.job_combo.setCurrentText(""); grab(ro, "readonly", lang); ro.close()
    # settings (gear)
    win._open_settings(); grab(win._settings_dialog, "settings", lang); win._settings_dialog.close()
    # dialogs
    d = RenameContainerDialog(win, level="inner", serial="I26080011", scan_ready=False)
    d.new_edit.setText("I26089011"); d.show(); grab(d, "rename", lang); d.close()
    d = ChildRelabelDialog(win, "inner", "I26080011", "I26089011",
                           [{"serial_no": f"I26080011-D{k}", "level": "display", "children": 4} for k in (1, 2, 3)])
    d.show(); grab(d, "rename_children", lang); d.close()
    d = DeleteContainerDialog(win, table="filling_product_logs", level="inner", serial="I26080011")
    d._preview_timer.stop(); d._update_preview(); d.show(); grab(d, "delete", lang); d.close()
    LOG.entries.clear()
    LOG.add('Serial "U2608999901" is already in use — pick another.')
    lg = LogWindow(win); lg.show(); grab(lg, "log", lang); lg.close()
    win.close()

for lang in ("en", "th"):
    shoot(lang)
print(sorted(os.listdir(OUT)))
