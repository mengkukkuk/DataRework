"""Run one db.* call off the Qt UI thread, and get the result back on it.

Every db.* call blocks for a full network round trip, and until now every
call site in main_window.py/container_panel.py ran that call directly on the
UI thread -- freezing the window for the duration. This module is the one
place that offload lives, so a call site stays a single function call instead
of hand-rolling QThread/QRunnable plumbing each time.

QRunnable cannot emit signals itself, so each job gets a small QObject to
carry them (_WorkerSignals). That object -- not the lambda a caller passes in
-- is what `succeeded`/`failed` are connected to, and its own bound methods
are the actual Qt slots: PySide only auto-marshals a cross-thread signal to
the *receiver's* thread when the receiver is a QObject it can identify, which
a plain lambda closing over `self` is not. Routing delivery through the
signals object's own methods (built, and therefore thread-affined, on the UI
thread by run_async) is what makes on_success/on_error land on the UI thread
regardless of what kind of callable the caller passed.
"""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

# One worker thread: keeps concurrent DB-connection checkouts bounded and
# predictable against db/connection.py's small pool, and avoids two in-flight
# jobs racing to populate the same UI state out of order.
_pool = QThreadPool()
_pool.setMaxThreadCount(1)

# Keeps each in-flight job's signals object referenced until delivery, so it
# is not garbage-collected while its emit() is still queued for the UI
# thread's event loop.
_inflight = {}


class _WorkerSignals(QObject):
    _succeeded = Signal(object, object)
    _failed = Signal(object, object)

    def __init__(self, key, on_success, on_error):
        super().__init__()
        self._key = key
        self._on_success = on_success
        self._on_error = on_error
        self._succeeded.connect(self._deliver_success)
        self._failed.connect(self._deliver_error)

    def _deliver_success(self, result, request_id):
        _inflight.pop(self._key, None)
        if self._on_success:
            self._on_success(result, request_id)

    def _deliver_error(self, exc, request_id):
        _inflight.pop(self._key, None)
        if self._on_error:
            self._on_error(exc, request_id)


class _Job(QRunnable):
    def __init__(self, fn, args, kwargs, signals, request_id):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs
        self._signals, self._request_id = signals, request_id

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # never let it escape run() unseen
            self._signals._failed.emit(exc, self._request_id)
        else:
            self._signals._succeeded.emit(result, self._request_id)


def run_async(fn, *args, on_success=None, on_error=None, request_id=None, **kwargs):
    """Run fn(*args, **kwargs) off the UI thread.

    on_success(result, request_id) or on_error(exc, request_id) is called
    back on the UI thread once the job finishes -- never both, and always
    exactly one of them, even if fn raises. `request_id` is opaque to this
    module; callers use it (typically a generation counter) to recognize and
    drop a result that arrives after something newer has superseded it.
    """
    key = object()
    signals = _WorkerSignals(key, on_success, on_error)  # built on the UI thread
    job = _Job(fn, args, kwargs, signals, request_id)
    _inflight[key] = (signals, job)
    _pool.start(job)


def shutdown(timeout_ms=3000):
    """Let in-flight work finish before the window that would receive its
    signals is torn down. Call from MainWindow.closeEvent."""
    _pool.waitForDone(timeout_ms)
