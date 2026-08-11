"""Census of invariant tests and the comments that cite them.

Every ``test_*`` name cited from a comment in ``modern_di/`` resolves to a real test, and every
``INVARIANT:`` docstring states what breaks it. A rename that orphans a citation fails here rather
than in review -- the citations are all that replaced the deleted ``architecture/`` pages.
"""

import ast
import pathlib
import re
import tokenize


_REPO_ROOT = pathlib.Path(__file__).parent.parent
_SRC_DIR = _REPO_ROOT / "modern_di"
_TESTS_DIR = _REPO_ROOT / "tests"

# `\b` before the lookahead forces the whole identifier, so `test_resolver_compiler.py`
# (a module name, not a citation) is rejected instead of matching a truncated prefix.
_CITATION = re.compile(r"\b(test_[a-z0-9_]+)\b(?!\.py)")
_INVARIANT = "INVARIANT:"
# The claim paragraph, then the "what breaks it" paragraph -- fewer than two means the second is missing.
_MIN_PARAGRAPHS = 2


def _test_functions() -> list[tuple[pathlib.Path, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found = []
    for path in sorted(_TESTS_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.extend(
            (path, node)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        )
    return found


def _cited_names(path: pathlib.Path) -> set[str]:
    """Names cited from real comments only -- tokenize, so a `#` inside a string is not a comment."""
    with path.open("rb") as handle:
        return {
            name
            for token in tokenize.tokenize(handle.readline)
            if token.type == tokenize.COMMENT
            for name in _CITATION.findall(token.string)
        }


def test_every_cited_test_exists() -> None:
    known = {node.name for _, node in _test_functions()}
    assert known, "the walk over tests/ found no test functions"

    orphans = sorted(
        f"{path.relative_to(_REPO_ROOT)}: {name}"
        for path in sorted(_SRC_DIR.rglob("*.py"))
        for name in _cited_names(path)
        if name not in known
    )
    assert not orphans, f"comments cite tests that do not exist: {orphans}"


def test_every_invariant_states_what_breaks_it() -> None:
    marked = [
        (path, node) for path, node in _test_functions() if (ast.get_docstring(node) or "").startswith(_INVARIANT)
    ]
    assert marked, "no test carries an INVARIANT: docstring; the convention is not in use"

    bare = sorted(
        f"{path.relative_to(_REPO_ROOT)}::{node.name}"
        for path, node in marked
        if len([part for part in (ast.get_docstring(node) or "").split("\n\n") if part.strip()]) < _MIN_PARAGRAPHS
    )
    assert not bare, f"INVARIANT tests with no 'what breaks it' paragraph: {bare}"
