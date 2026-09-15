# Login Prototype Design

## Purpose

A prototype desktop login window for this new project. On successful
login (verified against a mock Postgres `users` table) it routes to a
placeholder main app window. Plain, unstyled Qt widgets — no custom
QSS.

## Stack

- Python 3.13
- PySide6 (Qt for Python)
- psycopg2-binary (Postgres driver) — fallback to `psycopg[binary]`
  if psycopg2-binary fails to resolve on this Python version
- bcrypt (password hash verification)

Dependency versions are not pinned here; they are resolved empirically
by installing into `.venv` during implementation and recording what
actually resolves in `requirements.txt`.

## Existing data assumption

A `users` table already exists in `postgres`/`public` with at least
these columns:

- `username` (text)
- `password_hash` (text — assumed to be a bcrypt hash)

This design does not create or seed that table. If a queried
`password_hash` is not a valid bcrypt digest (or is `NULL`/empty),
`bcrypt.checkpw` raises `ValueError` or `TypeError` — both are treated
identically to "wrong password" (see Error handling).

## Modules

- `main.py` — entry point. Builds `QApplication`, shows `LoginWindow`.
- `login_window.py` — `LoginWindow(QWidget)`: username `QLineEdit`,
  password `QLineEdit` (echo mode = Password), "Login" `QPushButton`,
  and a hidden-until-needed error `QLabel`. Enter key in either field
  triggers login, same as clicking the button.
- `db.py` — `get_connection()` opens a psycopg2 connection to
  Postgres (`host=localhost`, `dbname=postgres`, `user=postgres`).
  The password is read from the `DB_PASSWORD` environment variable,
  defaulting to `P@ssw0rd` if unset, so the literal only ever appears
  as a fallback default, not as the sole source of the credential.
  `verify_user(username, password) -> bool` selects `password_hash`
  from `users` where `username = %s` (parameterized query) and checks
  it with `bcrypt.checkpw`, catching `ValueError`/`TypeError` as a
  non-match. The connection is closed after each call via
  `contextlib.closing`.
- `main_window.py` — `MainWindow(QMainWindow)`: a placeholder window
  with a single `QLabel("Welcome, {username}")` in a central widget.

## Data flow

1. User enters username/password and clicks Login (or presses Enter).
2. `LoginWindow` calls `db.verify_user(username, password)`.
3. On `True`: `LoginWindow` closes itself and opens
   `MainWindow(username)`.
4. On `False`: inline error label shows "Invalid username or
   password", password field is cleared, window stays open.

## Error handling

- Wrong credentials (unknown username, bad password, or a
  non-bcrypt/`NULL` `password_hash`): same inline message — "Invalid
  username or password" — regardless of cause, so the UI never
  reveals which part was wrong.
- Database unreachable / connection error: caught around the
  `verify_user` call, shown via the same inline error label as
  "Unable to reach the database"; the real exception is logged to
  the console for debugging.

## Testing

Manual, since this is a prototype with no existing test harness:

1. Run the app; log in with a valid user from the `users` table →
   expect the placeholder main window with "Welcome, {username}".
2. Log in with a valid username and wrong password → expect inline
   "Invalid username or password".
3. Log in with an unknown username → expect the same inline error.
4. Stop Postgres and attempt login → expect "Unable to reach the
   database".

## Out of scope

- Creating/seeding the `users` table.
- Session management, logout, password reset, or any real app
  functionality behind the main window (it's a placeholder).
- Automated tests.
