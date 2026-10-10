"""Runs the ```python blocks under docs/ as tests (`just test-docs`).

Blocks on one page share a namespace, in page order. A block that is not meant to run carries
`<!-- skip: next "reason" -->` above its fence; hidden setup goes in `<!-- invisible-code-block: python -->`.
A block that demonstrates an error carries `<!-- raises: ErrorClassName -->` and passes only if it raises that.
"""

import ast
import asyncio
import inspect
import pathlib
from collections.abc import Iterator

import pytest
from sybil import Document, Example, Region, Sybil
from sybil.parsers.markdown import ClearNamespaceParser, CodeBlockParser, SkipParser
from sybil.parsers.markdown.lexers import DirectiveInHTMLCommentLexer


_UNINSTALLED_PACKAGES = frozenset(
    {"aiohttp", "fastapi", "modern_di_litestar", "modern_di_pytest", "pydantic_ai", "redis", "sqlalchemy"}
)

_EXCLUDED_PAGES = (
    "adr/*",
    "agents/*",
    "migration/*",
)

_FRAMEWORK_INDEPENDENT_INTEGRATION_PAGES = frozenset({"writing-integrations.md"})

_EXPECTED_ERROR_KEY = "__docs_expected_error__"

_RAISES_LEXER = DirectiveInHTMLCommentLexer("raises", arguments=r"\w+")


def _expect_error(example: Example) -> None:
    example.namespace[_EXPECTED_ERROR_KEY] = example.parsed


def _parse_raises(document: Document) -> Iterator[Region]:
    for lexed in _RAISES_LEXER(document):
        yield Region(lexed.start, lexed.end, lexed.lexemes["arguments"], _expect_error)


def _run(example: Example) -> None:
    source = "\n" * (example.line + example.parsed.line_offset) + example.parsed
    code = compile(source, example.path, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, dont_inherit=True)
    result = eval(code, example.namespace)  # noqa: S307
    if inspect.iscoroutine(result):
        asyncio.run(result)


def _evaluate_python(example: Example) -> None:
    expected_error = example.namespace.pop(_EXPECTED_ERROR_KEY, None)
    try:
        _run(example)
    except ModuleNotFoundError as error:
        if (error.name or "").partition(".")[0] not in _UNINSTALLED_PACKAGES:
            raise
        pytest.skip(f"{error.name} is not installed in this repo")
    except Exception as error:
        if type(error).__name__ != expected_error:
            raise
        return
    if expected_error:
        pytest.fail(f"expected the block to raise {expected_error}, it raised nothing")


_collect_docs = Sybil(
    parsers=[
        CodeBlockParser("python", _evaluate_python),
        SkipParser(),
        ClearNamespaceParser(),
        _parse_raises,
    ],
    path="docs",
    patterns=["*.md"],
    excludes=_EXCLUDED_PAGES,
).pytest()


def pytest_collect_file(file_path: pathlib.Path, parent: pytest.Collector) -> pytest.Collector | None:
    if file_path.parent.name == "integrations" and file_path.name not in _FRAMEWORK_INDEPENDENT_INTEGRATION_PAGES:
        return None
    return _collect_docs(file_path, parent)
