# CLAUDE.md

Guidance for Claude Code when working in this existing PySide6 desktop project.
This file is project-agnostic: **discover the real structure first, then follow it.** Do not reorganize the project to match this document.

## 1. First steps in any session

1. Detect the layout before editing anything:
   - Find the entry point (`main.py`, `app.py`, `__main__.py`, or a `[project.scripts]` entry in `pyproject.toml`).
   - Find all `*.ui` and `*.qrc` files and their generated counterparts (`ui_*.py`, `*_rc.py`, `*_ui.py`, or a `ui/` / `generated/` package).
   - Read `requirements.txt` / `pyproject.toml` to confirm the PySide6 version and any PLC, database, or plotting libraries.
2. Follow the project's existing naming and folder conventions, even if they differ from the examples below.
3. If a convention is unclear, ask before introducing a new one.

## 2. Environment

- Language: Python 3.10+ (check the project's pinned version).
- GUI: **PySide6** (Qt for Python). Never mix in PyQt5/PyQt6 imports.
- Use the project's virtual environment (`.venv` / `venv`). Do not install packages globally.
- Windows is the primary platform. Use `pathlib.Path` for paths, never hard-coded backslashes.
- Run the app with the project's existing command; if none is documented, use `python main.py` (adjust to the detected entry point).

## 3. Qt Designer / UIC workflow

- `.ui` files are the **source of truth** for layout. Generated `ui_*.py` files are build output.
- **Never hand-edit generated files** (`ui_*.py`, `*_rc.py`). Changes are lost on the next compile.
- To change a layout:
  1. Edit the `.ui` file (Qt Designer: `pyside6-designer <file>.ui`). If you cannot open Designer, edit the XML minimally and carefully.
  2. Regenerate: `pyside6-uic <file>.ui -o <dir>/ui_<file>.py`
  3. For resources: `pyside6-rcc <file>.qrc -o <dir>/<file>_rc.py`
- If the project loads `.ui` at runtime with `QUiLoader`, keep doing so; do not switch approaches without being asked.
- After regenerating, check that existing widget `objectName` references in the logic code still resolve. Renaming a widget in Designer requires updating every `self.ui.<name>` usage.
- Keep UI logic in a separate class (e.g. `MainWindow(QMainWindow)`) that **uses** the generated `Ui_*` class via composition (`self.ui = Ui_MainWindow(); self.ui.setupUi(self)`).

## 4. Code conventions

- Follow the existing style (formatter, line length, quote style). If `ruff`, `black`, or `flake8` config exists, respect it and run it on changed files.
- Type hints on new public functions and methods.
- Use the modern signal/slot syntax: `button.clicked.connect(self.on_start)`.
- Mark slots with `@Slot()` (from `PySide6.QtCore`) when they are connected to cross-thread signals.
- Prefer `Signal` definitions on the class body; name them in past tense or as events (`data_received`, `connection_lost`).
- Keep widgets out of business logic. Models, PLC drivers, and database code must be importable and testable without a `QApplication`.
- Use `logging` (module-level `logger = logging.getLogger(__name__)`), not `print`.
- No wildcard imports from `PySide6`.

## 5. Threading rules (critical)

The GUI thread must never block.

- **Never** do any of these on the GUI thread: PLC reads/writes, socket I/O, database queries, file parsing, `time.sleep`.
- Run blocking work in a worker:
  - Preferred: a `QObject` worker moved to a `QThread` with `moveToThread`, or `QThreadPool` + `QRunnable` for short jobs.
  - For periodic polling, use a worker with its own loop or a `QTimer` **inside the worker thread**.
- **Only the GUI thread touches widgets.** Workers communicate exclusively through signals. Never call `label.setText(...)` or similar from a worker.
- Shut down cleanly: stop the worker, call `thread.quit()` and `thread.wait()` in `closeEvent`. Do not leave threads running at exit.
- Emit small, copyable payloads in signals (dicts, dataclasses, tuples). Do not pass mutable shared state.

Worker skeleton:

```python
from PySide6.QtCore import QObject, QThread, Signal, Slot


class PollWorker(QObject):
    data_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, interval_ms: int = 500):
        super().__init__()
        self._interval_ms = interval_ms
        self._running = False

    @Slot()
    def run(self):
        self._running = True
        while self._running:
            try:
                self.data_ready.emit(self._read_once())
            except Exception as exc:  # report, do not crash the thread
                self.error.emit(str(exc))
            QThread.msleep(self._interval_ms)
        self.finished.emit()

    def stop(self):
        self._running = False

    def _read_once(self) -> dict:
        raise NotImplementedError
```

## 6. PLC / industrial communication (Mitsubishi FX5U)

Applies only if the project talks to a PLC. Check the existing driver module first and extend it rather than adding a second one.

- Keep all PLC access behind one driver/service class (connect, read, write, close). The UI never talks to the PLC directly.
- Use batch reads over many single-device reads to reduce scan load and latency.
- Always handle: connection timeout, reconnect with backoff, and partial/invalid responses.
- Treat writes as dangerous: validate address, type, and range before sending. Never add auto-write or "test write" behavior to live devices without explicit confirmation.
- Do not hard-code IP addresses, ports, or device maps. Read them from the project's config file.
- Document device addresses (D, M, X, Y registers) in one place (config or a mapping module), not scattered in UI code.

## 7. Database (if present)

- Use the project's existing access layer (SQLAlchemy, psycopg, or plain SQL). Do not mix styles.
- Parameterized queries only. Never build SQL with string formatting.
- Database calls run off the GUI thread (see section 5).
- Never commit credentials. Read connection settings from env vars or the existing config.

## 8. Plotting and real-time display

- If the project uses `pyqtgraph`, reuse existing plot widgets. Update data with `setData` on existing curves instead of recreating plots.
- Cap buffer sizes (e.g. `collections.deque(maxlen=N)`) for streaming data to avoid memory growth.
- Throttle UI updates (about 10-30 FPS is enough); batch incoming samples.

## 9. Testing and verification

- Before declaring a task done, at minimum:
  - Run the app entry point and confirm it starts with no import or traceback errors.
  - Run the existing test suite if present (`pytest`).
  - If a `.ui` file changed, confirm regenerated files are up to date.
- Logic code should be testable without a display. For widget tests use `pytest-qt` if it is already a dependency.
- Do not claim a GUI behavior works if you could not run it. State what was and was not verified.

## 10. Do / Don't

**Do**
- Make the smallest change that solves the task.
- Keep generated files in sync with their sources.
- Preserve existing public function names and signals unless asked to change them.
- Ask before adding new dependencies.

**Don't**
- Hand-edit `ui_*.py` or `*_rc.py`.
- Block the GUI thread.
- Touch widgets from worker threads.
- Rename or move project folders without being asked.
- Commit secrets, `.venv`, `__pycache__`, or build output.
- Rewrite working code just to match a preferred style.

## 11. Project-specific notes (fill in)

Replace these placeholders with real values so future sessions start faster.

- Entry point: `TODO`
- UI source folder: `TODO` (e.g. `ui/`)
- Generated UI folder: `TODO` (e.g. project root or `generated/`)
- UIC command used here: `TODO`
- Config file: `TODO`
- PLC driver module: `TODO`
- Run command: `TODO`
- Test command: `TODO`
