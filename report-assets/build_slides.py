"""Build ../slides.html from slides_template.html: embeds every screenshot as a data URI and
inlines the agents diagram from the report, so the deck is one file that still works when emailed.
reveal.js (vendor/reveal/, MIT license) is inlined too, so the deck needs no internet connection.

    cd calma/report-assets && python3 build_slides.py
"""

import base64
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def embed(m: re.Match) -> str:
    name, alt, cls = m.group(1), m.group(2), m.group(3) or ""
    path = HERE / name
    data = base64.b64encode(path.read_bytes()).decode()
    c = f' class="{cls}"' if cls else ""
    return f'<img{c} src="data:{MIME[path.suffix.lower()]};base64,{data}" alt="{alt}">'


def agents_svg() -> str:
    """Reuse Figure 2 from the report so the deck and the report show the same diagram."""
    report = (HERE / "report_template.html").read_text(encoding="utf-8")
    i = report.index("<h3>How they are organized")
    a = report.index("<svg", i)
    b = report.index("</svg>", a) + len("</svg>")
    svg = report[a:b]
    return svg  # keeps its own sans-serif labels, which are sized to fit the boxes


html = (HERE / "slides_template.html").read_text(encoding="utf-8")
html = html.replace("{{svg:agents}}", agents_svg())
html = re.sub(r"\{\{inline-css:([^}]+)\}\}", lambda m: "<style>\n" + (HERE / m.group(1)).read_text(encoding="utf-8") + "\n</style>", html)
html = re.sub(r"\{\{inline-js:([^}]+)\}\}", lambda m: "<script>\n" + (HERE / m.group(1)).read_text(encoding="utf-8").replace("</script", "<\\/script") + "\n</script>", html)
out = re.sub(r"\{\{img:([^|}]+)\|([^|}]*)(?:\|([^}]*))?\}\}", embed, html)
assert not re.search(r"\{\{(img|svg|inline)", out), "unreplaced placeholder"
assert not re.search(r'(src|href)="https?://(?!github\.com|calma-)', out.split("<body>")[0]), "external resource left in <head>"
(HERE.parent / "slides.html").write_text(out, encoding="utf-8")
print(f"wrote slides.html ({len(out) / 1e6:.1f} MB)")
