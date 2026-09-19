# Split db.py into a db/ package + atomic grid save

Decomposition **A2** (lean package, call-time connection lookup). Scope: extraction only,
plus one behaviour fix — unify the grid-save transaction.

Out of scope, deliberately untouched: `authenticate()`'s disabled bcrypt check, the rename
TOCTOU on `_serial_in_use`, any SQL/schema change, GUI redesign.

---

## 1. Target layout

`db.py` is **deleted** — a `db.py` and a `db/` cannot coexist on `sys.path`.

| File | Moved from `db.py` |
|---|---|
| `db/connection.py` | `DB_HOST/NAME/USER/PASSWORD`, `get_connection()` (8-19) |
| `db/auth.py` | `authenticate()` (21-43), incl. the commented-out bcrypt block verbatim |
| `db/schema.py` | `get_columns()`, `get_primary_key_columns()` (46-75) |
| `db/queries.py` | `fetch_distinct_values()`, `query_rows()`, `save_changes()` (78-149) + new `_save_changes(cur, ...)` |
| `db/hierarchy.py` | `LEVELS`, `CONTAINER_LEVELS`, `STAGING_EDGE_TABLE`, `SERIAL_DATA_TABLE`, `SharedEdgeError`, `SerialConflictError` (165-188) |
| `db/serial_state.py` | `_set_serial_active(cur, ...)` (272-282) — shared by mirror *and* rename |
| `db/edge_mirror.py` | 5 mirror helpers (191-269), `update_staging_serial_data()` (285-365) + new `_update_staging_serial_data(cur, ...)` + new `save_grid_changes()` |
| `db/containers.py` | 3 rename helpers + the 5 public container ops (377-611) |
| `db/__init__.py` | explicit re-exports + `__all__` (new) |

Existing public signatures and return shapes are unchanged. Three new functions only:
`queries._save_changes`, `edge_mirror._update_staging_serial_data`, `edge_mirror.save_grid_changes`.

## 2. The connection contract

Every submodule that opens a connection does:

```python
from . import connection
...
with contextlib.closing(connection.get_connection()) as conn:
```

Never `from .connection import get_connection` inside an implementation module — that would
capture the function and defeat patching. `db/__init__.py` re-exports it as an *alias* so
`from db import get_connection` (serial_store_aio.py:18) keeps working.

Consequence, accepted: `db.get_connection` is no longer the patch point.
`tests/_test_container_rename.py:84` becomes:

```diff
-db.get_connection = lambda: NoCommit(real)
+db.connection.get_connection = lambda: NoCommit(real)
```

`@patch("db.get_columns")` / `@patch("db.container_serials")` etc. keep working untouched,
because `main_window.py` / `rename_dialog.py` still resolve `db.X` at call time.

`db/__init__.py` imports `connection` **first**, so the import-time `os.environ` read keeps
its current timing (entry points load `.env` before importing `db`). No `load_dotenv` is
added anywhere inside `db`.

## 3. `db/__init__.py`

```python
"""Public database API for the GUI and the serial-store sync."""

# First: credentials are captured from os.environ when this is imported.
from . import connection
from .connection import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, get_connection
from .hierarchy import (LEVELS, CONTAINER_LEVELS, STAGING_EDGE_TABLE,
                        SERIAL_DATA_TABLE, SharedEdgeError, SerialConflictError)
from .auth import authenticate
from .schema import get_columns, get_primary_key_columns
from .queries import fetch_distinct_values, query_rows, save_changes
from .edge_mirror import update_staging_serial_data, save_grid_changes
from .containers import (container_serials, container_children, rename_children,
                         container_rename_preview, rename_container)

__all__ = [...]  # every name above, plus "connection"
```

The explicit imports (not `__all__`) are what PyInstaller's static analysis follows;
`serial_state` is reached via `edge_mirror`/`containers`. `hiddenimports=[]` stays empty.

## 4. Shared transaction

**Cursor-only, no connection/commit/rollback/exception-translation:**
- `queries._save_changes(cur, table, pk_columns, updates, deletes, schema)` — the UPDATE/DELETE loops (123-147) moved verbatim.
- `edge_mirror._update_staging_serial_data(cur, updates, deletes, pk_columns, schema, table)` — the full existing algorithm: resolve pk_column, fetch originals, **complete** the shared-edge validation pass and raise `SharedEdgeError` before any write, then apply mirror updates / activation flips / unit-edge deletes. SQL and params unchanged. `UniqueViolation` propagates raw to the owner.

**Connection owners:**
- `queries.save_changes(...)` and `edge_mirror.update_staging_serial_data(...)` keep their current standalone behaviour exactly (own connection, own commit, own `UniqueViolation` translation, own empty-input no-op) — they now just delegate the SQL to the cursor helpers.
- New `edge_mirror.save_grid_changes(table, pk_columns, updates, deletes, schema="public")`:
  returns `None` without opening a connection when `updates` and `deletes` are both empty;
  otherwise one connection, one cursor, mirror then grid, **one commit**; `UniqueViolation`
  from either phase or the commit becomes `SerialConflictError` with the existing message and
  `__cause__`; every other exception rolls back and re-raises unchanged so
  `psycopg2.OperationalError` still reaches `main_window.py:805`. Rollback failures are
  suppressed so they cannot mask the original error.

**GUI diff** (`main_window.py:800-804`) — the only production consumer change:

```diff
         try:
-            # Mirrors the edit into staging_product_logs first: it refuses the
-            # save on a shared container before filling_product_logs is touched.
-            db.update_staging_serial_data(updates, deletes, self._pk_columns)
-            db.save_changes(STAGING_TABLE, self._pk_columns, updates, deletes)
+            # One transaction: the mirror refuses a shared container before
+            # filling_product_logs is touched, and a later failure rolls both back.
+            db.save_grid_changes(STAGING_TABLE, self._pk_columns, updates, deletes)
```

All five `except` clauses at 805-813 stay as they are.

## 5. Dependency graph (acyclic)

```
__init__  -> connection, hierarchy, auth, schema, queries, edge_mirror, containers
auth      -> connection
schema    -> connection
queries   -> connection
edge_mirror -> connection, hierarchy, serial_state, queries
containers  -> connection, hierarchy, serial_state
serial_state -> hierarchy
connection, hierarchy -> (no project modules)
```

## 6. Build order

1. **Baseline** — run `test_i18n.py` and `test_identifier_values.py`, record the starting state.
2. **Extraction** — create the 9 package files, delete `db.py`, retarget the patch in
   `_test_container_rename.py`. Bodies unchanged at this point; no `save_grid_changes` yet.
   *Verify:* both existing suites still pass, `import db` resolves to the package.
3. **Cursor helpers** — carve `_save_changes` and `_update_staging_serial_data` out; legacy
   public functions delegate to them. *Verify:* existing suites still pass.
4. **`save_grid_changes`** + facade export. *Verify:* new `tests/test_db_package.py`.
5. **GUI switch** — apply the `main_window.py` diff. *Verify:* full `test_*.py` run.
6. **Report** — what still needs a live/isolated DB and a `build.ps1` rebuild to confirm.

## 7. New tests — `tests/test_db_package.py` (one file, mock-based)

Deliberately narrower than a full matrix; covers only what the refactor actually puts at risk:

- Every connection-owning public op routes through `db.connection.get_connection` **after**
  import — patched with a sentinel, with `psycopg2.connect` patched to fail if reached.
  This is the regression that would otherwise let `_test_container_rename.py` commit to the
  live DB.
- Facade exception objects are identical to `db.hierarchy`'s (so `except db.SharedEdgeError`
  at main_window.py:808 still catches).
- `save_grid_changes`: empty input opens no connection; success = one connection, one cursor
  shared by both phases, one commit, no rollback; a failure in the grid phase after a
  successful mirror phase rolls back and does not commit; `UniqueViolation` -> `SerialConflictError`;
  `OperationalError` propagates unchanged.
- `SharedEdgeError` is raised before any mirror/activation/grid write.

Follows the repo convention: `QT_QPA_PLATFORM=offscreen` at the top, `unittest`,
`unittest.mock.patch`, no live DB.

## 8. Verification that needs a human / environment

- Isolated-DB check that a deliberately failed save leaves edge rows, `activate` flags and
  filling rows untouched. Mocks prove the orchestration, not that PostgreSQL undid the writes.
- `build.ps1` rebuild of both exes (it stops/restarts the installed sync service) to confirm
  PyInstaller finds all 8 submodules with `hiddenimports=[]`.
