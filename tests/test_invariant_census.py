"""Census of invariant tests and the citations that point to them.

Every ``test_*`` name cited from a comment or docstring under ``modern_di/`` or ``tests/``
resolves to a real test, every ``tests/<name>.py`` or ``planning/<slug>.md`` path cited the same
way resolves to a real file, and every ``INVARIANT:`` docstring states what breaks it. A rename
that orphans a citation fails here rather than in review -- the citations are all that replaced
the deleted prose documentation pages.
"""

import ast
import pathlib
import re
import tokenize


_REPO_ROOT = pathlib.Path(__file__).parent.parent
_SRC_DIR = _REPO_ROOT / "modern_di"
_TESTS_DIR = _REPO_ROOT / "tests"
_BENCHMARKS_DIR = _REPO_ROOT / "benchmarks"
_DECISIONS_DIR = _REPO_ROOT / "planning" / "decisions"
_DEFERRED_DIR = _REPO_ROOT / "planning" / "deferred"
# Markdown scanned for test-name citations. Scoped deliberately -- docs/ uses illustrative
# user-facing test names (e.g. docs/recipes/testing-overrides.md) that are not real tests here.
_MD_CITATION_SOURCES = (
    _REPO_ROOT / "CLAUDE.md",
    *sorted(_DECISIONS_DIR.glob("*.md")),
    *sorted(_DEFERRED_DIR.glob("*.md")),
)

# `\b` before the lookahead forces the whole identifier, so `test_resolver_compiler.py`
# (a module name, not a citation) is rejected instead of matching a truncated prefix.
_CITATION = re.compile(r"\b(test_[a-z0-9_]+)\b(?!\.py)")
# A `tests/<name>.py` or `planning/<slug>.md` path, or a bare dated `planning/` filename cited
# without its directory prefix (e.g. `2026-07-26-explicit-only-validation.md`).
_PATH_CITATION = re.compile(r"\b((?:tests|planning)/[\w./-]+\.(?:py|md)|\d{4}-\d{2}-\d{2}-[\w-]+\.md)\b")
_INVARIANT = "INVARIANT:"
# The claim paragraph, then the "what breaks it" paragraph -- fewer than two means the second is missing.
_MIN_PARAGRAPHS = 2

# Module included so a module-level docstring counts; ast.walk yields it before its descendants.
_DOCSTRING_NODE_TYPES = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _walk_test_functions(root: pathlib.Path) -> list[tuple[pathlib.Path, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.extend(
            (path, node)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        )
    return found


def _test_functions() -> list[tuple[pathlib.Path, ast.FunctionDef | ast.AsyncFunctionDef]]:
    return _walk_test_functions(_TESTS_DIR)


def _citation_paths() -> list[pathlib.Path]:
    return sorted({*_SRC_DIR.rglob("*.py"), *_TESTS_DIR.rglob("*.py")})


def _comment_matches(path: pathlib.Path, pattern: re.Pattern[str]) -> set[str]:
    """Names matching `pattern` in real comments only -- tokenize, so a `#` inside a string is not a comment."""
    with path.open("rb") as handle:
        return {
            name
            for token in tokenize.tokenize(handle.readline)
            if token.type == tokenize.COMMENT
            for name in pattern.findall(token.string)
        }


def _docstring_matches(path: pathlib.Path, pattern: re.Pattern[str]) -> set[str]:
    """Names matching `pattern` in any module/class/function docstring in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, _DOCSTRING_NODE_TYPES):
            docstring = ast.get_docstring(node)
            if docstring:
                names.update(pattern.findall(docstring))
    return names


def _comment_citations(path: pathlib.Path) -> set[str]:
    return _comment_matches(path, _CITATION)


def _docstring_citations(path: pathlib.Path) -> set[str]:
    return _docstring_matches(path, _CITATION)


def _path_citation_exists(citation: str) -> bool:
    """Resolve `citation`: a full path directly, a bare dated filename under `decisions/`/`deferred/`."""
    if citation.startswith(("tests/", "planning/")):
        return (_REPO_ROOT / citation).is_file()
    return (_DECISIONS_DIR / citation).is_file() or (_DEFERRED_DIR / citation).is_file()


def test_every_cited_test_exists() -> None:
    known = {node.name for _, node in _test_functions()}
    assert known, "the walk over tests/ found no test functions"

    orphans = sorted(
        f"{path.relative_to(_REPO_ROOT)}: {name}"
        for path in _citation_paths()
        for name in _comment_citations(path) | _docstring_citations(path)
        if name not in known
    )
    assert not orphans, f"comments or docstrings cite tests that do not exist: {orphans}"


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


def test_every_cited_path_and_markdown_test_name_exists() -> None:
    """Guard two citation forms `test_every_cited_test_exists` misses.

    A path cited from a `modern_di/`/`tests/` comment or docstring, and a test name cited from
    `CLAUDE.md` or a `planning/decisions/`/`planning/deferred/` record -- neither trips the
    name-only, Python-only check above, since one is spelled as a path and the other lives outside
    `.py` files.
    """
    path_orphans = sorted(
        f"{path.relative_to(_REPO_ROOT)}: {citation}"
        for path in _citation_paths()
        for citation in _comment_matches(path, _PATH_CITATION) | _docstring_matches(path, _PATH_CITATION)
        if not _path_citation_exists(citation)
    )
    assert not path_orphans, f"comments or docstrings cite paths that do not exist: {path_orphans}"

    known = {node.name for _, node in _test_functions()}
    known |= {node.name for _, node in _walk_test_functions(_BENCHMARKS_DIR)}
    assert known, "the walk over tests/ and benchmarks/ found no test functions"

    md_orphans = sorted(
        f"{md_path.relative_to(_REPO_ROOT)}: {name}"
        for md_path in _MD_CITATION_SOURCES
        for name in _CITATION.findall(md_path.read_text(encoding="utf-8"))
        if name not in known
    )
    assert not md_orphans, f"Markdown cites tests that do not exist: {md_orphans}"
