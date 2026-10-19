"""Append-only audit trail of what operators did, one file per day:
logs/audit-YYYY-MM-DD.log.

Sits next to logs/serial_store_sync.log (the sync service's output) but is
separate: that one is machine noise, this one answers "who changed what, from
which VM, when". One line per activity:

    [time: 2026-10-19 12:44:32, VM_ID: 1, tag_name: ADMIN, Activities: Save - 2 update(s)]

debug_log.LOG stays in memory on purpose (it quotes tracebacks); this file is the
opposite -- short, deliberate entries that are meant to be kept. Recording never
raises: a full disk or locked file must not stop the operator's real action.
"""
import datetime
import logging
import os
import sys
from pathlib import Path

LOG_PREFIX = "audit-"
LOG_SUFFIX = ".log"

_logger = logging.getLogger("datarework.audit")
_logger.setLevel(logging.INFO)
_logger.propagate = False  # not into the root logger / console

_tag_name = ""
_failed = False


def _log_dir():
    # Override for tests / a shared location; default is logs/ beside the app,
    # the same folder the sync service's serial_store_sync.log goes to.
    override = os.environ.get("AUDIT_LOG_DIR", "").strip()
    if override:
        return Path(override)
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent
    return base / "logs"


def log_path(day):
    return _log_dir() / f"{LOG_PREFIX}{day:%Y-%m-%d}{LOG_SUFFIX}"


class _DailyFileHandler(logging.FileHandler):
    """Writes to today's file, opening a new one when the date changes.

    Chosen over TimedRotatingFileHandler, which renames audit.log at rollover:
    that only fires in a process that is running at midnight, so a GUI left open
    overnight or opened the next morning would mix days. Here the file is picked
    from the clock on every record, so each day's file holds only that day.
    """

    def __init__(self):
        self._day = datetime.date.today()
        log_path(self._day).parent.mkdir(exist_ok=True)
        super().__init__(log_path(self._day), encoding="utf-8", delay=True)

    def emit(self, record):
        today = datetime.date.today()
        if today != self._day:
            self.close()  # FileHandler reopens lazily on the next emit
            self._day = today
            self.baseFilename = os.path.abspath(log_path(today))
        super().emit(record)


def _ensure_handler():
    if _logger.handlers:
        return
    handler = _DailyFileHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)


def set_session(tag_name):
    """Remember who is signed in, so call sites only need to say what happened."""
    global _tag_name
    _tag_name = "" if tag_name is None else str(tag_name)


def format_entry(activity, tag_name=None, when=None):
    when = when or datetime.datetime.now()
    tag = _tag_name if tag_name is None else str(tag_name)
    vm_id = os.environ.get("VM_ID", "").strip()
    # One entry per line: an embedded newline would read as a second entry.
    activity = " ".join(str(activity).split())
    return (f"[time: {when:%Y-%m-%d %H:%M:%S}, VM_ID: {vm_id}, "
            f"tag_name: {tag}, Activities: {activity}]")


def record(activity, tag_name=None):
    """Write one audit line. Returns True if written; never raises."""
    global _failed
    try:
        _ensure_handler()
        _logger.info(format_entry(activity, tag_name))
        _failed = False
        return True
    except Exception:
        # Say so once per outage on stderr (NSSM/console), not on every action.
        if not _failed:
            _failed = True
            logging.getLogger(__name__).exception("could not write the audit log")
        return False
