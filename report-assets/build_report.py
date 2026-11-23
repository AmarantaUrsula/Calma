"""Build ../report.html from report_template.html, embedding every image as a data URI
so the report is a single file that still works when emailed.

    cd calma/report-assets && python3 build_report.py
"""

import base64
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def embed(match: re.Match) -> str:
    name, alt = match.group(1), match.group(2)
    path = HERE / name
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:{MIME[path.suffix.lower()]};base64,{data}" alt="{alt}">'


html = (HERE / "report_template.html").read_text(encoding="utf-8")
out = re.sub(r"\{\{img:([^|}]+)\|([^}]*)\}\}", embed, html)
missing = re.findall(r"\{\{img:", out)
assert not missing, "unreplaced image placeholders"
(HERE.parent / "report.html").write_text(out, encoding="utf-8")
print(f"wrote report.html ({len(out) / 1e6:.1f} MB)")
