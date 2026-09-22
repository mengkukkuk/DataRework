import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time
import unittest

from PySide6.QtWidgets import QApplication

import db_worker


def _pump_until(app, predicate, timeout_s=3.0):
    """Process the Qt event loop until `predicate()` is true or time runs out.

    The worker runs on a real background thread; its signal only reaches the
    UI-thread slot once this thread's event loop gets a turn to deliver it.
    """
    deadline = time.time() + timeout_s
    while not predicate() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    return predicate()


class DbWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.main_thread = threading.current_thread()

    def test_success_delivers_the_result_on_the_ui_thread(self):
        calls = []
        db_worker.run_async(
            lambda: 42,
            on_success=lambda result, req: calls.append((result, req, threading.current_thread())),
            on_error=lambda exc, req: self.fail(f"on_error fired unexpectedly: {exc}"),
        )
        self.assertTrue(_pump_until(self.app, lambda: calls))
        result, _req, thread = calls[0]
        self.assertEqual(result, 42)
        self.assertIs(thread, self.main_thread)

    def test_a_raised_exception_reaches_on_error_and_not_on_success(self):
        errors = []

        def boom():
            raise ValueError("boom")

        db_worker.run_async(
            boom,
            on_success=lambda result, req: self.fail(f"on_success fired unexpectedly: {result}"),
            on_error=lambda exc, req: errors.append(exc),
        )
        self.assertTrue(_pump_until(self.app, lambda: errors))
        self.assertIsInstance(errors[0], ValueError)
        self.assertEqual(str(errors[0]), "boom")

    def test_request_id_is_passed_through_unchanged(self):
        calls = []
        db_worker.run_async(
            lambda: None,
            on_success=lambda result, req: calls.append(req),
            request_id=("search", 7),
        )
        self.assertTrue(_pump_until(self.app, lambda: calls))
        self.assertEqual(calls[0], ("search", 7))

    def test_positional_and_keyword_arguments_are_forwarded(self):
        calls = []
        db_worker.run_async(
            lambda a, b, c=None: (a, b, c),
            1, 2, c=3,
            on_success=lambda result, req: calls.append(result),
        )
        self.assertTrue(_pump_until(self.app, lambda: calls))
        self.assertEqual(calls[0], (1, 2, 3))

    def test_a_stale_result_can_be_dropped_by_the_caller_via_request_id(self):
        # Mirrors how main_window.py uses request_id as a generation counter:
        # only the result tagged with the latest generation is kept.
        applied = []
        latest_generation = [2]

        def on_success(result, generation):
            if generation != latest_generation[0]:
                return
            applied.append(result)

        db_worker.run_async(lambda: "stale", on_success=on_success, request_id=1)
        db_worker.run_async(lambda: "fresh", on_success=on_success, request_id=2)
        self.assertTrue(_pump_until(self.app, lambda: len(applied) >= 1))
        # Give the (already-serialized, single-thread pool) stale job a chance
        # to have been delivered too, so this isn't just "fresh arrived first".
        _pump_until(self.app, lambda: False, timeout_s=0.2)
        self.assertEqual(applied, ["fresh"])


if __name__ == "__main__":
    unittest.main()
