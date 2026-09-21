from __future__ import annotations

import re
from pathlib import Path
from typing import Any


HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
SLUG_STRIP = re.compile(r"[^a-z0-9\s-]")


def slug(title: str) -> str:
    value = SLUG_STRIP.sub("", title.lower()).strip()
    return re.sub(r"[\s-]+", "-", value) or "section"


def _headings(lines: list[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING.match(line)
        if match:
            found.append(
                {"level": len(match["hashes"]), "title": match["title"].strip(), "line": number}
            )
    return found


def outline(path: Path) -> list[dict[str, Any]]:
    """A section runs to the next heading at its own level or above, so it carries its subsections."""
    if not path.is_file():
        raise FileNotFoundError(str(path))
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    headings = _headings(lines)
    sections: list[dict[str, Any]] = []
    trail: list[tuple[int, str]] = []
    used: dict[str, int] = {}
    for index, heading in enumerate(headings):
        while trail and trail[-1][0] >= heading["level"]:
            trail.pop()
        identifier = "/".join([part for _, part in trail] + [slug(heading["title"])])
        seen = used.get(identifier, 0)
        used[identifier] = seen + 1
        if seen:
            identifier = f"{identifier}-{seen + 1}"
        trail.append((heading["level"], slug(heading["title"])))
        following = next(
            (later for later in headings[index + 1 :] if later["level"] <= heading["level"]), None
        )
        end = following["line"] - 1 if following else len(lines)
        sections.append(
            {
                "id": identifier,
                "title": heading["title"],
                "level": heading["level"],
                "start_line": heading["line"],
                "end_line": end,
                "lines": end - heading["line"] + 1,
            }
        )
    return sections


def body(path: Path, section: dict[str, Any]) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[section["start_line"] - 1 : section["end_line"]])
