# Implementation Report: Container Rename

## Summary

`display_serial_no` / `carton_serial_no` name a *container* shared by many
`filling_product_logs` rows (6 per display, ~130 per carton), so editing them as a
per-row grid cell was never coherent. Measured against the live `rpadata` database
before any change:

- editing `display_serial_no` was **always blocked** — `SharedEdgeError` fires for
  every display, because every display has siblings;
- editing `carton_serial_no` **silently corrupted data** — `filling_product_logs`
  took the new name while `staging_product_logs` kept the old one (0 rows changed).
  Cause: `_edge_id_column()` assumes a `{level}_source_id` column, but `carton_source_id`
  does not exist (carton is the root), so both the guard and the write were skipped.

Those columns are now read-only in the grid, and renaming is an explicit
right-click action that rewrites the whole container in one transaction.

## Decisions taken from the user

| Question | Decision |
|---|---|
| Rename scope | By container — right-click a container cell → "Rename this display / carton…" |
| Duplicate protection | App-side check (no unique constraint exists on `staging_product_logs`) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | `db.CONTAINER_LEVELS`, `container_rename_preview()`, `rename_container()` | Complete | Scoped by serial + label code, not by a row's edge id |
| 2 | Read-only container cells + right-click rename in `main_window.py` | Complete | |
| 3 | `tests/_test_container_rename.py` | Complete | 24 checks |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static analysis | Pass | `py_compile` clean on both modules; no linter configured in this repo |
| Unit tests | Pass | 24 new checks; DB assertions run against live data and roll back |
| Regression | Pass | Existing `tests/_test_highlight.py` — 6/6 still green |
| Build | Not run | `build.ps1` stops/starts the NSSM sync service and needs elevation — deferred to the user |
| Edge cases | Pass | See table below |
| Data safety | Pass | Post-run counts unchanged: 60 edge rows, 277 filling rows, 0 synthetic rows persisted |

### Edge cases covered

| Case | Behaviour |
|---|---|
| Rename onto a serial already in use | Refused — `SerialConflictError` |
| Rename a container that does not exist | Refused — `SerialConflictError` |
| Rename to the same / empty serial | Refused — `ValueError` |
| `unit` passed as a container level | Refused — `ValueError` |
| Right-click on unit serial or a plain column | No menu action offered |
| Pending unsaved cell edits at rename time | Blocked with a status message, so the reload cannot discard them |
| Carton (no `carton_source_id` column) | Rename reaches both tables — the original silent no-op |

## Files Changed

| File | Action | Notes |
|---|---|---|
| `db.py` | UPDATED | +~125 lines: `CONTAINER_LEVELS`, `_container_edge_counts`, `container_rename_preview`, `rename_container` |
| `main_window.py` | UPDATED | +~95 lines: `CONTAINER_SERIAL_COLUMNS`, `READONLY_COLUMNS`, `_on_table_context_menu`, `_rename_container`, read-only flags/tooltips |
| `tests/_test_container_rename.py` | CREATED | 24 checks |

`git diff --stat` against HEAD shows larger numbers because the working tree already
carried unrelated in-progress edits to both files before this task started.

## Key Implementation Detail

A container is matched by **serial + label code**, never by a row's
`{level}_source_id`:

```sql
UPDATE staging_product_logs SET serial_no        = :new
 WHERE serial_no        = :old AND serial_label_code        = :level;
UPDATE staging_product_logs SET parent_serial_no = :new
 WHERE parent_serial_no = :old AND parent_serial_label_code = :level;
UPDATE filling_product_logs SET <level>_serial_no = :new
 WHERE <level>_serial_no = :old;
```

Going through one row's edge id can only ever fix that row. A display is named both
by its own `display->carton` edge *and* by the `parent_serial_no` of all ~6
`unit->display` edges beneath it, so the rename must hit every edge naming the
container at once or the two tables disagree. The label-code predicate keeps a
display rename from touching a unit that happens to share the string.

## Deviations from Plan

| What | Why |
|---|---|
| "Move this unit to another display" not implemented | Item 3 of the original recommendation; the user's instruction only settled the rename, so it was left out rather than guessed at |
| `_edge_id_column()` / `_apply_edge_change()` left untouched | Item 4. With container cells read-only, `_changed_levels()` can now only ever return `unit`, for which the existing path is correct. Rewriting it would have widened the blast radius for no behavioural gain |
| Container `*_roll_no` made read-only with no replacement editor | Neither level's roll edit ever worked (display was blocked, carton no-oped), so no working capability was removed. Flagged below |
| No feature branch created | Working tree already held the user's uncommitted work on both files; implemented in place on `master` to avoid moving it |

## Known Gaps

- `SerialConflictError`'s docstring cites `uq_staging_product_logs_business_key`.
  **That constraint does not exist** on this database, so the `UniqueViolation`
  handler in `update_staging_serial_data` is unreachable. The new duplicate check is
  app-side precisely because of this. Adding the real constraint would be the
  durable fix.
- `display_roll_no` / `carton_roll_no` are now read-only with no rename equivalent.
- `*_source_id` / `*_target_id` remain editable; hand-editing them still corrupts
  the graph. Out of scope here.

## Follow-up: two-stage rename UI

The right-click action was a single `QInputDialog` prompt — it could only rename
the container you happened to be looking at, and nothing carried down to what that
container holds. Replaced with an explicit button and two panels.

**Stage 1 — `RenameContainerDialog`.** A `Rename container…` button in the footer
opens a level rail (`Carton │ Inner │ Display`, outermost first — the levels are a
containment order, so a segmented control shows that where a dropdown would not),
a container picker, and the `old ──▶ new` pair. Both serials are set in the same
monospace face with widened tracking, so the eye compares them digit by digit;
`letter-spacing` has no QSS equivalent, so it is applied via `QFont` in
`rename_dialog._serial_font()`. A live line under the pair states the blast radius
before the user commits.

**Stage 2 — `ChildRelabelDialog`.** After the rename commits, every direct child is
listed under the container's *new* name, each with the count of what sits beneath
it. New serials are pre-filled by substituting the parent's old serial inside the
child's (`suggest_child_serial`) — right whenever children are named off their
container, and a no-op otherwise. Ticked rows apply in one atomic
`db.rename_children` call. The right-click menu still works and now pre-selects
the dialog instead of prompting.

| File | Action | Notes |
|---|---|---|
| `rename_dialog.py` | CREATED | Both dialogs + `suggest_child_serial` |
| `db.py` | UPDATED | `container_serials`, `container_children`, `rename_children`; `_serial_in_use` / `_apply_serial_rename` factored out of `rename_container` and shared with the batch path |
| `main_window.py` | UPDATED | Footer button, `_relabel_children`, `QInputDialog` → `QDialog` |
| `style.css` | UPDATED | 6 tokens per theme + dialog rules; no existing selector touched |
| `tests/_test_container_rename.py` | UPDATED | 24 → 49 checks |

Batch safety, all covered by tests: an empty batch is a no-op; two children given
the same new serial is refused; an A→B/B→A swap is refused with a two-step
instruction rather than half-applied; one bad entry aborts the whole batch and
leaves the good entries unwritten.

## Next Steps

- [ ] Rebuild via `build.ps1` (elevated — stops/starts `DataReworkSerialStoreSync`)
- [ ] Manual GUI pass: footer button → rename a carton → confirm the child panel
- [ ] Code review via `/code-review`
