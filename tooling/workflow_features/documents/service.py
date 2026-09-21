from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tooling.workflow_config import load_workflow_settings
from tooling.workflow_features.documents.outline import body, outline


MARKDOWN = ("*.md", "*.markdown")

STOPWORDS = frozenset(
    "a an and are as at be by do does for from how i if in is it its of on or "
    "that the then there these this to was what when where which who why with you your".split()
)


def _resolve(project_root: Path, relative: str) -> Path:
    path = (project_root / relative).resolve()
    if not path.is_relative_to(project_root.resolve()):
        raise ValueError(f"Path escapes the project: {relative}")
    return path


def _table_of_contents(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: section[key] for key in ("id", "title", "level", "lines")} for section in sections
    ]


def document_outline(project_root: Path, relative: str) -> dict[str, Any]:
    path = _resolve(project_root, relative)
    sections = outline(path)
    total = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    settings = load_workflow_settings(project_root)
    return {
        "path": relative,
        "lines": total,
        "sections": _table_of_contents(sections),
        "read_whole_file": total <= settings.document_whole_file_lines or not sections,
    }


def read_section(project_root: Path, relative: str, section_id: str) -> dict[str, Any]:
    """Every section answer carries the full table of contents, so the agent sees what it skipped."""
    path = _resolve(project_root, relative)
    sections = outline(path)
    match = next((section for section in sections if section["id"] == section_id), None)
    if match is None:
        raise ValueError(
            f"Unknown section '{section_id}' in {relative}. Known ids: "
            + ", ".join(section["id"] for section in sections)
        )
    return {
        "path": relative,
        "section": {key: match[key] for key in ("id", "title", "level", "start_line", "end_line")},
        "content": body(path, match),
        "table_of_contents": _table_of_contents(sections),
    }


def _candidates(project_root: Path, roots: list[str]) -> list[Path]:
    found: list[Path] = []
    for relative in roots or ["."]:
        base = _resolve(project_root, relative)
        if base.is_file():
            found.append(base)
            continue
        for pattern in MARKDOWN:
            found.extend(
                path
                for path in base.rglob(pattern)
                if ".git" not in path.parts and "node_modules" not in path.parts
            )
    return sorted(set(found))


def find_sections(
    project_root: Path, query: str, roots: list[str], limit: int
) -> dict[str, Any]:
    """Lexical on purpose: a ranked list an agent can check, not a similarity score it must trust."""
    words = [term for term in re.split(r"\W+", query.lower()) if term]
    if not words:
        raise ValueError("Search needs at least one word")
    terms = [term for term in words if term not in STOPWORDS] or words
    hits: list[dict[str, Any]] = []
    for path in _candidates(project_root, roots):
        relative = path.relative_to(project_root.resolve()).as_posix()
        try:
            sections = outline(path)
        except (OSError, UnicodeDecodeError):
            continue
        for section in sections:
            content = body(path, section)
            text = content.lower()
            title = section["title"].lower()
            matched = [term for term in terms if term in text or term in title]
            if not matched:
                continue
            weight = sum(4 * title.count(term) + text.count(term) for term in terms)
            hits.append(
                {
                    "path": relative,
                    "id": section["id"],
                    "title": section["title"],
                    "lines": section["lines"],
                    "matched_terms": matched,
                    "density": round(weight / section["lines"], 4),
                    "excerpt": _excerpt(content, terms),
                    "start_line": section["start_line"],
                    "end_line": section["end_line"],
                }
            )
    hits = _narrowest(hits)
    hits.sort(
        key=lambda hit: (-len(hit["matched_terms"]), -hit["density"], hit["path"], hit["id"])
    )
    return {"query": query, "terms": terms, "matches": hits[:limit], "total": len(hits)}


def _narrowest(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A parent contains its children, so it answers broadly where a child answers precisely."""
    kept = []
    for hit in hits:
        contains_another = any(
            other is not hit
            and other["path"] == hit["path"]
            and hit["start_line"] <= other["start_line"]
            and other["end_line"] <= hit["end_line"]
            for other in hits
        )
        if not contains_another:
            kept.append({key: value for key, value in hit.items() if key not in ("start_line", "end_line")})
    return kept


def _excerpt(content: str, terms: list[str]) -> str:
    for line in content.splitlines()[1:]:
        stripped = line.strip()
        if stripped and any(term in stripped.lower() for term in terms):
            return stripped[:200]
    return next((line.strip()[:200] for line in content.splitlines()[1:] if line.strip()), "")
