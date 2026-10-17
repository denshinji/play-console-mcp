"""Reads store listing text from the listing-<language>.md files in docs/store/play.

Each file has one `##` section per field; the heading may carry a character
count in parentheses, which is ignored:

    ## Nama aplikasi (6/30)
    Contoh
"""

from __future__ import annotations

import re
from pathlib import Path

LIMITS = {"title": 30, "shortDescription": 80, "fullDescription": 4000}

_HEADINGS = {
    "nama aplikasi": "title",
    "app name": "title",
    "title": "title",
    "deskripsi singkat": "shortDescription",
    "short description": "shortDescription",
    "deskripsi lengkap": "fullDescription",
    "full description": "fullDescription",
}

_FILE_NAME = re.compile(r"^listing-(?P<language>[A-Za-z]{2,3}(?:-[A-Za-z0-9]+)?)\.md$")


def language_of(path: Path) -> str | None:
    match = _FILE_NAME.match(path.name)
    return match["language"] if match else None


def parse_listing(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []

    def flush() -> None:
        if current:
            fields[current] = "\n".join(lines).strip()

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            heading = re.sub(r"\(.*?\)", "", line[3:]).strip().lower()
            current = _HEADINGS.get(heading)
            lines = []
        elif line.startswith("# "):
            flush()
            current, lines = None, []
        elif current:
            lines.append(line)
    flush()
    return fields


def length_errors(fields: dict[str, str]) -> list[str]:
    return [
        f"{name} is {len(value)} characters; the limit is {LIMITS[name]}"
        for name, value in fields.items()
        if name in LIMITS and len(value) > LIMITS[name]
    ]
