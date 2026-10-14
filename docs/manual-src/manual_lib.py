"""Shared pieces for the user manual: page styling, small HTML helpers, PDF rendering.

The manual is one self-contained HTML file per language (images are inlined as
base64), so it can be mailed or copied to a shared drive on its own. The PDF is
printed from that same HTML by headless Microsoft Edge -- no third-party service
is involved and nothing leaves the machine.
"""
import base64
import html
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"

CSS = r"""
:root {
  --bg: #f4f6f9; --paper: #ffffff; --ink: #1c2733; --muted: #5a6b7d; --line: #d9e0e8;
  --accent: #2c6aa0; --accent-soft: #e6f0f9; --navy: #263a4f;
  --note-bg: #eaf3fb; --note-line: #2c6aa0;
  --tip-bg: #e9f6ef; --tip-line: #2f9e66;
  --warn-bg: #fff4e0; --warn-line: #d98a0b;
  --stop-bg: #fdecec; --stop-line: #c8453f;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: "Segoe UI", "Leelawadee UI", "Noto Sans Thai", Tahoma, sans-serif;
  font-size: 16px; line-height: 1.6;
}
html[lang="th"] body { line-height: 1.8; }
.layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); max-width: 1320px; margin: 0 auto; }
nav.toc {
  position: sticky; top: 0; align-self: start; height: 100vh; overflow-y: auto;
  padding: 28px 18px 28px 24px; border-right: 1px solid var(--line); font-size: 14px;
}
nav.toc .brand { font-weight: 700; font-size: 17px; color: var(--navy); margin-bottom: 4px; }
nav.toc .sub { color: var(--muted); margin-bottom: 16px; font-size: 13px; }
nav.toc ol { list-style: none; margin: 0; padding: 0; }
nav.toc li { margin: 0; }
nav.toc a { display: block; padding: 4px 8px; border-radius: 6px; color: var(--ink); text-decoration: none; line-height: 1.4; }
nav.toc a:hover { background: var(--accent-soft); color: var(--accent); }
nav.toc .langswitch { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line); }
main { padding: 28px 40px 80px; min-width: 0; }
.paper { background: var(--paper); border: 1px solid var(--line); border-radius: 10px; padding: 36px 44px; }

.cover { padding: 56px 0 40px; border-bottom: 3px solid var(--accent); margin-bottom: 28px; }
.cover .kicker { text-transform: uppercase; letter-spacing: .12em; color: var(--accent); font-weight: 700; font-size: 13px; }
html[lang="th"] .cover .kicker { text-transform: none; letter-spacing: .04em; }
.cover h1 { font-size: 40px; line-height: 1.15; margin: 8px 0 12px; color: var(--navy); }
.cover p.lead { font-size: 18px; color: var(--muted); max-width: 40em; margin: 0 0 18px; }
.cover .meta { font-size: 13px; color: var(--muted); }

section.chapter { margin-top: 36px; }
h2 { font-size: 26px; color: var(--navy); border-bottom: 2px solid var(--line); padding-bottom: 6px; margin: 0 0 14px; }
h2 .num { color: var(--accent); margin-right: 8px; }
h3 { font-size: 19px; color: var(--navy); margin: 26px 0 8px; }
h4 { font-size: 16px; margin: 18px 0 6px; color: var(--ink); }
p { margin: 8px 0; }
ul, ol { margin: 8px 0 8px 1.3em; padding: 0; }
li { margin: 4px 0; }
code, kbd { font-family: Consolas, "Cascadia Mono", monospace; font-size: .92em; }
code { background: #eef2f6; border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; }
kbd { background: #fff; border: 1px solid #b9c4d0; border-bottom-width: 2px; border-radius: 5px; padding: 0 6px; white-space: nowrap; }
.ui { font-weight: 600; color: var(--navy); }
.btn {
  display: inline-block; padding: 0 9px; border-radius: 6px; background: var(--navy); color: #fff;
  font-size: .9em; font-weight: 600; line-height: 1.55; white-space: nowrap;
}
.btn.light { background: #e4e9f0; color: var(--navy); }
.btn.green { background: #3aae72; color: #06301c; }
.btn.red { background: #e3a1ae; color: #4a0d1a; }
.btn.blue { background: #5b9bd5; color: #fff; }
.tab { display: inline-block; padding: 0 9px; border: 1px solid var(--line); border-bottom: 3px solid var(--accent); border-radius: 5px 5px 0 0; background: #fff; font-weight: 600; font-size: .92em; white-space: nowrap; }
.msg { font-family: Consolas, "Cascadia Mono", "Leelawadee UI", monospace; font-size: .88em; background: #f1f4f8; border-left: 3px solid #9aa9ba; padding: 1px 7px; border-radius: 3px; overflow-wrap: anywhere; }

.callout { margin: 14px 0; padding: 10px 16px 10px 14px; border-left: 5px solid var(--note-line); background: var(--note-bg); border-radius: 0 8px 8px 0; break-inside: avoid; }
.callout > .t { font-weight: 700; margin-bottom: 2px; }
.callout p:first-of-type { margin-top: 0; } .callout p:last-child { margin-bottom: 0; }
.callout.tip { border-color: var(--tip-line); background: var(--tip-bg); }
.callout.warn { border-color: var(--warn-line); background: var(--warn-bg); }
.callout.stop { border-color: var(--stop-line); background: var(--stop-bg); }

figure { margin: 18px 0; break-inside: avoid; }
figure .frame { position: relative; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #eef1f5; line-height: 0; box-shadow: 0 2px 8px rgba(30,45,60,.08); }
figure.narrow .frame { max-width: 560px; margin: 0 auto; }
figure img { width: 100%; height: auto; display: block; }
figcaption { font-size: 13.5px; color: var(--muted); margin-top: 6px; line-height: 1.5; text-align: center; }
.mark {
  position: absolute; transform: translate(-50%, -50%); width: 22px; height: 22px; border-radius: 50%;
  background: #d9381e; color: #fff; font: 700 12px/22px "Segoe UI", Tahoma, sans-serif; text-align: center;
  border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,.4);
}

table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14.5px; }
th, td { border: 1px solid var(--line); padding: 7px 10px; text-align: left; vertical-align: top; }
th { background: #eaf0f6; color: var(--navy); font-weight: 700; }
tr { break-inside: avoid; }
tbody tr:nth-child(even) td { background: #fafbfd; }
td.yes { color: #1f7a4d; font-weight: 700; text-align: center; }
td.no { color: #b23b35; font-weight: 700; text-align: center; }
.legend { columns: 2; column-gap: 28px; margin: 8px 0 0 1.4em; }
.legend li { break-inside: avoid; }
.chain { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 14px 0; }
.chain .lvl { padding: 7px 14px; border-radius: 8px; font-weight: 700; border-top: 4px solid; background: #fff; border-left: 1px solid var(--line); border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.chain .arrow { color: var(--muted); font-size: 13px; }
.lvl.carton { border-top-color: #d98a0b; } .lvl.inner { border-top-color: #7a52c9; }
.lvl.display { border-top-color: #2c6aa0; } .lvl.unit { border-top-color: #2f9e66; }
.steps { counter-reset: s; list-style: none; margin-left: 0; }
.steps > li { counter-increment: s; position: relative; padding-left: 38px; margin: 10px 0; }
.steps > li::before {
  content: counter(s); position: absolute; left: 0; top: 1px; width: 27px; height: 27px; border-radius: 50%;
  background: var(--accent); color: #fff; font-weight: 700; text-align: center; line-height: 27px; font-size: 14px;
}
footer.end { margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }

@media (max-width: 900px) {
  .layout { display: block; } nav.toc { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  main { padding: 16px; } .paper { padding: 20px 16px; } .legend { columns: 1; }
  .cover h1 { font-size: 30px; } table { display: block; overflow-x: auto; }
}
@page { size: A4; margin: 15mm 14mm 16mm; }
@media print {
  :root { --bg: #fff; }
  body { font-size: 10.5pt; background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .layout { display: block; max-width: none; } nav.toc, .noprint { display: none !important; }
  main { padding: 0; } .paper { border: 0; padding: 0; border-radius: 0; }
  .cover { padding: 30mm 0 14mm; break-after: page; }
  .cover h1 { font-size: 34pt; }
  section.chapter { margin-top: 10mm; }
  figure.narrow .frame { max-width: 118mm; }
  h2 { font-size: 18pt; break-after: avoid; } h3 { font-size: 13.5pt; break-after: avoid; } h4 { break-after: avoid; }
  figure, .callout, .chain { break-inside: avoid; }
  figure img { max-height: 235mm; width: auto; max-width: 100%; margin: 0 auto; }
  table { font-size: 9.5pt; } thead { display: table-header-group; }
  a { color: inherit; text-decoration: none; }
}
"""


def esc(text):
    return html.escape(str(text), quote=False)


def data_uri(name):
    raw = (SHOTS / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def figure(name, caption, marks=None, narrow=False, alt=""):
    """A screenshot with an optional set of numbered callouts.

    `marks` is [(number, x, y)] in pixels of the screenshot, converted to
    percentages so the numbers stay on their targets at any width.
    """
    header = (SHOTS / name).read_bytes()[:24]  # PNG IHDR: width, height as big-endian ints
    width, height = int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    dots = "".join(
        f'<span class="mark" style="left:{x / width * 100:.2f}%;top:{y / height * 100:.2f}%">{n}</span>'
        for n, x, y in (marks or [])
    )
    return (
        f'<figure class="{"narrow" if narrow else ""}"><div class="frame">'
        f'<img src="{data_uri(name)}" alt="{esc(alt or caption)}">{dots}</div>'
        f"<figcaption>{caption}</figcaption></figure>"
    )


def callout(kind, title, body):
    return f'<div class="callout {kind}"><div class="t">{title}</div>{body}</div>'


def table(headers, rows, cls=""):
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for row in rows:
        body += "<tr>" + "".join(
            f'<td class="{c[1]}">{c[0]}</td>' if isinstance(c, tuple) else f"<td>{c}</td>" for c in row
        ) + "</tr>"
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def steps(items):
    return '<ol class="steps">' + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


def bullets(items):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def find_edge():
    for candidate in (
        shutil.which("msedge"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ):
        if candidate and os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError("Microsoft Edge (msedge.exe) was not found; it is used to print the PDF.")


def html_to_pdf(html_path, pdf_path):
    edge = find_edge()
    profile = Path(os.environ.get("TEMP", ".")) / "datarework_manual_edge_profile"
    cmd = [
        edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}",
        Path(html_path).resolve().as_uri(),
    ]
    subprocess.run(cmd, check=True, timeout=180, capture_output=True)
