from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LanguageSyntax:
    """How to reach the import statements of one language without reading its prose."""

    patterns: tuple[re.Pattern[str], ...]
    line_comments: tuple[str, ...] = ("//",)
    block_comments: tuple[tuple[str, str], ...] = (("/*", "*/"),)
    quotes: tuple[str, ...] = ('"', "'")
    strip_triple_quoted: bool = False
    extra: tuple[str, ...] = field(default=())


def _compile(*expressions: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(expression, re.MULTILINE) for expression in expressions)


PYTHON = LanguageSyntax(
    patterns=_compile(
        r"^[ \t]*from[ \t]+([A-Za-z_.][\w.]*)[ \t]+import\b",
        r"^[ \t]*import[ \t]+([A-Za-z_][\w.]*)",
    ),
    line_comments=("#",),
    block_comments=(),
    strip_triple_quoted=True,
)

CSHARP = LanguageSyntax(
    patterns=_compile(r"^[ \t]*(?:global[ \t]+)?using[ \t]+(?:static[ \t]+)?(?:\w+[ \t]*=[ \t]*)?([\w.]+)[ \t]*;")
)

ECMASCRIPT = LanguageSyntax(
    patterns=_compile(
        r"""^[ \t]*import[ \t]+[^;'"]*from[ \t]*['"]([^'"]+)['"]""",
        r"""^[ \t]*import[ \t]*['"]([^'"]+)['"]""",
        r"""^[ \t]*export[ \t]+[^;'"]*from[ \t]*['"]([^'"]+)['"]""",
        r"""\brequire\([ \t]*['"]([^'"]+)['"]""",
        r"""\bimport\([ \t]*['"]([^'"]+)['"]""",
    ),
    quotes=('"', "'", "`"),
)

DART = LanguageSyntax(patterns=_compile(r"""^[ \t]*(?:import|export|part)[ \t]+['"]([^'"]+)['"]"""))

GO = LanguageSyntax(patterns=_compile(r"""^[ \t]*import[ \t]+(?:[\w.]+[ \t]+)?["`]([^"`]+)["`]"""), quotes=('"', "`"))

RUST = LanguageSyntax(
    patterns=_compile(
        r"^[ \t]*(?:pub[ \t]+)?use[ \t]+([\w:]+)",
        r"^[ \t]*(?:pub[ \t]+)?extern[ \t]+crate[ \t]+(\w+)",
    )
)

JVM = LanguageSyntax(patterns=_compile(r"^[ \t]*import[ \t]+(?:static[ \t]+)?([\w.]+(?:\.\*)?)"))

CFAMILY = LanguageSyntax(patterns=_compile(r"""^[ \t]*#[ \t]*include[ \t]*[<"]([^>"]+)[>"]"""))

RUBY = LanguageSyntax(
    patterns=_compile(r"""^[ \t]*require(?:_relative)?[ \t]*\(?[ \t]*['"]([^'"]+)['"]"""),
    line_comments=("#",),
    block_comments=(),
)

PHP = LanguageSyntax(
    patterns=_compile(
        r"^[ \t]*use[ \t]+([\w\\]+)",
        r"""^[ \t]*(?:require|require_once|include|include_once)[ \t]*\(?[ \t]*['"]([^'"]+)['"]""",
    ),
    line_comments=("//", "#"),
)

SYNTAX_BY_SUFFIX: dict[str, LanguageSyntax] = {
    ".py": PYTHON,
    ".cs": CSHARP,
    ".js": ECMASCRIPT,
    ".jsx": ECMASCRIPT,
    ".ts": ECMASCRIPT,
    ".tsx": ECMASCRIPT,
    ".dart": DART,
    ".go": GO,
    ".rs": RUST,
    ".java": JVM,
    ".kt": JVM,
    ".c": CFAMILY,
    ".cc": CFAMILY,
    ".cpp": CFAMILY,
    ".h": CFAMILY,
    ".hpp": CFAMILY,
    ".rb": RUBY,
    ".php": PHP,
}

GO_IMPORT_BLOCK = re.compile(r"^[ \t]*import[ \t]*\((.*?)^[ \t]*\)", re.DOTALL | re.MULTILINE)
GO_BLOCK_ENTRY = re.compile(r"""["`]([^"`]+)["`]""")


def strip_non_code(text: str, syntax: LanguageSyntax) -> str:
    """Remove comments while leaving string literals and line structure intact."""
    result: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if syntax.strip_triple_quoted and (text.startswith('"""', index) or text.startswith("'''", index)):
            token = text[index : index + 3]
            end = text.find(token, index + 3)
            end = length if end == -1 else end + 3
            result.append("\n" * text.count("\n", index, end))
            index = end
            continue
        if character in syntax.quotes:
            index = _append_string_literal(text, index, character, result)
            continue
        comment_end = _line_comment_end(text, index, syntax)
        if comment_end is not None:
            index = comment_end
            continue
        block = _block_comment_span(text, index, syntax)
        if block is not None:
            result.append("\n" * text.count("\n", index, block))
            index = block
            continue
        result.append(character)
        index += 1
    return "".join(result)


def _append_string_literal(text: str, index: int, quote: str, result: list[str]) -> int:
    length = len(text)
    cursor = index + 1
    while cursor < length:
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == quote:
            cursor += 1
            break
        if text[cursor] == "\n" and quote != "`":
            break
        cursor += 1
    result.append(text[index:cursor])
    return cursor


def _line_comment_end(text: str, index: int, syntax: LanguageSyntax) -> int | None:
    for token in syntax.line_comments:
        if text.startswith(token, index):
            end = text.find("\n", index)
            return len(text) if end == -1 else end
    return None


def _block_comment_span(text: str, index: int, syntax: LanguageSyntax) -> int | None:
    for opening, closing in syntax.block_comments:
        if text.startswith(opening, index):
            end = text.find(closing, index + len(opening))
            return len(text) if end == -1 else end + len(closing)
    return None


def extract_imports(text: str, suffix: str) -> set[str]:
    syntax = SYNTAX_BY_SUFFIX.get(suffix)
    if syntax is None:
        return set()
    code = strip_non_code(text, syntax)
    imports = {match.group(1) for pattern in syntax.patterns for match in pattern.finditer(code)}
    if syntax is GO:
        for block in GO_IMPORT_BLOCK.findall(code):
            imports.update(GO_BLOCK_ENTRY.findall(block))
    return {value for value in imports if value}
