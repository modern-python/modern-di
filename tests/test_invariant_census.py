"""Census of the invariant tests themselves.

Every ``INVARIANT:`` docstring states what breaks it: the claim alone is a label, and the second
paragraph is the anti-refactor warning.
"""

import ast
import pathlib


_REPO_ROOT = pathlib.Path(__file__).parent.parent
_TESTS_DIR = _REPO_ROOT / "tests"

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
