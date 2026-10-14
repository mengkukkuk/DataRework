"""Regenerate the user manual: docs/manual.html + manual.pdf (English) and
docs/manual.th.html + manual.th.pdf (Thai).

    .venv\\Scripts\\python.exe docs\\manual-src\\build_manual.py

The HTML files are self-contained (screenshots are inlined). The PDFs are printed
locally by headless Microsoft Edge -- no online conversion service is used.
To refresh the screenshots first, run docs\\manual-src\\shoot.py (fake data only).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from manual_content import build  # noqa: E402
from manual_lib import html_to_pdf  # noqa: E402

DOCS = HERE.parent
OUTPUTS = {"en": "manual", "th": "manual.th"}


def main(make_pdf=True):
    for lang, stem in OUTPUTS.items():
        html_path = DOCS / f"{stem}.html"
        html_path.write_text(build(lang), encoding="utf-8")
        print(f"wrote {html_path} ({html_path.stat().st_size // 1024} KB)")
        if make_pdf:
            pdf_path = DOCS / f"{stem}.pdf"
            html_to_pdf(html_path, pdf_path)
            print(f"wrote {pdf_path} ({pdf_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(make_pdf="--no-pdf" not in sys.argv)
