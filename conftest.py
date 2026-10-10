"""Runs the ```python blocks under docs/ as tests (`just test-docs`).

Blocks on one page share a namespace, in page order. A block that is not meant to run carries
`<!-- skip: next "reason" -->` above its fence; hidden setup goes in `<!-- invisible-code-block: python -->`.
"""

import ast
import asyncio
import inspect

import pytest
from sybil import Example, Sybil
from sybil.parsers.markdown import ClearNamespaceParser, CodeBlockParser, SkipParser


_UNINSTALLED_PACKAGES = frozenset(
    {"aiohttp", "fastapi", "modern_di_litestar", "modern_di_pytest", "pydantic_ai", "redis", "sqlalchemy"}
)

_EXCLUDED_PAGES = (
    "adr/*",
    "agents/*",
    "integrations/*",
    "migration/*",
)


def _evaluate_python(example: Example) -> None:
    source = "\n" * (example.line + example.parsed.line_offset) + example.parsed
    code = compile(source, example.path, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, dont_inherit=True)
    try:
        result = eval(code, example.namespace)  # noqa: S307
        if inspect.iscoroutine(result):
            asyncio.run(result)
    except ModuleNotFoundError as error:
        if (error.name or "").partition(".")[0] not in _UNINSTALLED_PACKAGES:
            raise
        pytest.skip(f"{error.name} is not installed in this repo")


pytest_collect_file = Sybil(
    parsers=[CodeBlockParser("python", _evaluate_python), SkipParser(), ClearNamespaceParser()],
    path="docs",
    patterns=["*.md"],
    excludes=_EXCLUDED_PAGES,
).pytest()
