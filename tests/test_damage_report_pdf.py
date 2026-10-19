"""damage_report_pdf: the Damage Report PDF layout and file output."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import datetime
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

import damage_report_pdf as pdf
from i18n import language

UTC = datetime.timezone.utc


def _row(serial, damaged_at=None, **extra):
    row = {"serial_no": serial, "level": "Qr Code", "roll_no": "R1", "box_no": "B1",
           "damaged_at": damaged_at, "last_user": "VM001"}
    row.update(extra)
    return row


class DamageReportPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        saved = language.code
        settings = patch("i18n.QSettings")
        settings.start()
        self.addCleanup(settings.stop)
        self.addCleanup(language.set, saved)
        language.set("en")
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_html_lists_each_serial_with_range_and_count(self):
        start = datetime.datetime(2026, 10, 1, 8, 0)
        end = datetime.datetime(2026, 10, 2, 17, 30)
        when = datetime.datetime(2026, 10, 1, 9, 5, tzinfo=UTC)
        text = pdf.build_html([_row("U1", when), _row("U2", when)],
                              start, end, generated_by="ADMIN", vm_id="7")
        for expected in ("U1", "U2", "2026-10-01 08:00 to 2026-10-02 17:30", "ADMIN", "<thead>"):
            self.assertIn(expected, text)

    def test_no_range_says_all_time_and_marks_serials_with_unknown_time(self):
        text = pdf.build_html([_row("U1"), _row("U2")])
        self.assertIn("All time", text)
        self.assertIn("Not recorded", text)

    def test_all_optional_columns_print_by_default(self):
        text = pdf.build_html([_row("U1", level="Display Box", roll_no="R9", box_no="B9")])
        for expected in ("Type", "Roll no", "Box no", "Display Box", "R9", "B9"):
            self.assertIn(expected, text)

    def test_unticked_columns_are_left_out_of_heading_and_rows(self):
        text = pdf.build_html([_row("U1", level="Display Box", roll_no="R9", box_no="B9")],
                              columns={"roll_no"})
        self.assertIn("Roll no", text)
        self.assertIn("R9", text)
        for absent in (">Type<", "Box no", "Display Box", "B9"):
            self.assertNotIn(absent, text)
        self.assertNotIn("R9", pdf.build_html([_row("U1", roll_no="R9")], columns=set()))

    def test_an_empty_report_spans_the_columns_actually_shown(self):
        self.assertIn('colspan="4"', pdf.build_html([], columns=set()))
        self.assertIn('colspan="7"', pdf.build_html([]))

    def test_default_folder_comes_from_env(self):
        with patch.dict(os.environ, {"DAMAGE_REPORT_DIR": self.dir.name}):
            self.assertEqual(pdf.default_folder(), self.dir.name)
        with patch.dict(os.environ, {"DAMAGE_REPORT_DIR": ""}):
            self.assertTrue(os.path.isdir(pdf.default_folder()))

    def test_values_are_html_escaped(self):
        text = pdf.build_html([_row("<b>X</b>&")])
        self.assertIn("&lt;b&gt;X&lt;/b&gt;&amp;", text)
        self.assertNotIn("<b>X</b>&", text)

    def test_an_empty_result_still_produces_a_readable_page(self):
        self.assertIn("No damaged serials in this range.", pdf.build_html([]))

    def test_thai_headings_follow_the_language(self):
        language.set("th")
        self.assertIn("รายงานความเสียหาย", pdf.build_html([_row("U1")]))

    def test_export_writes_a_pdf_and_long_lists_span_pages(self):
        path = str(Path(self.dir.name) / "out.pdf")
        pdf.export_pdf(path, [_row(f"U{n:05d}") for n in range(400)])
        data = Path(path).read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        pages = re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data)
        self.assertGreater(len(pages), 1)

    def test_a_missing_folder_is_an_error_not_a_silent_no_op(self):
        with self.assertRaises(OSError):
            pdf.export_pdf(str(Path(self.dir.name) / "nope" / "out.pdf"), [_row("U1")])

    def test_default_filename_is_dated(self):
        name = pdf.default_filename(datetime.datetime(2026, 10, 19, 13, 5, 42))
        self.assertEqual(name, "damage_report_20261019_130542.pdf")


if __name__ == "__main__":
    unittest.main()
