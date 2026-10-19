"""audit_log: one [time, VM_ID, tag_name, Activities] line per operator action."""
import datetime
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audit_log


def _reset():
    for handler in list(audit_log._logger.handlers):
        handler.close()
        audit_log._logger.removeHandler(handler)
    audit_log.set_session("")


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.addCleanup(_reset)
        patcher = patch.dict(os.environ, {"AUDIT_LOG_DIR": self.dir.name, "VM_ID": "7"})
        patcher.start()
        self.addCleanup(patcher.stop)
        _reset()

    def lines(self):
        return self.read(datetime.date.today())

    def read(self, day):
        path = Path(self.dir.name) / f"audit-{day:%Y-%m-%d}.log"
        return path.read_text(encoding="utf-8").splitlines()

    def test_line_has_time_vm_tag_and_activity(self):
        audit_log.set_session("ADMIN")
        self.assertTrue(audit_log.record("Save - 2 update(s)"))
        self.assertRegex(
            self.lines()[0],
            r"^\[time: \d{4}-\d\d-\d\d \d\d:\d\d:\d\d, VM_ID: 7, tag_name: ADMIN, "
            r"Activities: Save - 2 update\(s\)\]$")

    def test_each_record_is_its_own_line_appended(self):
        audit_log.record("Login")
        audit_log.record("Logout")
        self.assertEqual(len(self.lines()), 2)
        self.assertIn("Login", self.lines()[0])
        self.assertIn("Logout", self.lines()[1])

    def test_newlines_in_the_activity_cannot_forge_a_second_entry(self):
        audit_log.record('Rename "a\n[time: x]" -> "b"')
        self.assertEqual(len(self.lines()), 1)

    def test_explicit_tag_name_beats_the_session(self):
        audit_log.set_session("ADMIN")
        audit_log.record("Login", tag_name="OP-2")
        self.assertIn("tag_name: OP-2,", self.lines()[0])

    def test_a_new_day_starts_a_new_file(self):
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        audit_log.record("Login")
        with patch("audit_log.datetime") as fake:
            fake.date.today.return_value = tomorrow
            fake.datetime.now.return_value = datetime.datetime.combine(
                tomorrow, datetime.time(0, 0, 5))
            audit_log.record("Logout")
        self.assertEqual(len(self.read(today)), 1)
        self.assertIn("Login", self.read(today)[0])
        self.assertEqual(len(self.read(tomorrow)), 1)
        self.assertIn("Logout", self.read(tomorrow)[0])
        self.assertIn(f"time: {tomorrow:%Y-%m-%d} 00:00:05", self.read(tomorrow)[0])

    def test_unwritable_location_never_raises(self):
        blocker = Path(self.dir.name) / "file"
        blocker.write_text("x")
        with patch.dict(os.environ, {"AUDIT_LOG_DIR": str(blocker / "sub")}):
            _reset()
            self.assertFalse(audit_log.record("Login"))


if __name__ == "__main__":
    unittest.main()
