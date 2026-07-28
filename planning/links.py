# ruff: noqa: INP001  # planning/ is not a Python package (this file is vendored into consumers' planning/)
"""Check every relative Markdown link and heading anchor in the repository.

Run via ``just check-links``. Exists because a site builder only validates the
directory it publishes: a repo's ``architecture/`` and ``planning/`` trees usually
sit outside it, are read on GitHub, and rot silently. In the repo this convention
came from, anchors in ``architecture/`` broke three times in one week, each caught
only by a human re-deriving slugs by hand.

Slugs follow **GitHub's** algorithm, because that is where these files are read —
including the ones a site builder also publishes. Where the two disagree, the fix
is to change the heading rather than to teach this checker both dialects: a heading
containing an em dash yields ``a--b`` on GitHub (the dash is dropped, both spaces
become hyphens) and ``a-b`` under python-markdown (the whitespace run collapses).

External links are not fetched; this checks the repository's internal consistency.
"""

import argparse
import collections
import pathlib
import re
import sys


SKIP_DIRS = frozenset({".git", ".venv", ".tox", "site", "node_modules", "__pycache__", ".ruff_cache", ".superpowers"})
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"(`+).+?\1")  # any run of backticks delimits a span: `x`, ``a`b``
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)


def repo_root(start: pathlib.Path) -> pathlib.Path:
    """Nearest ancestor holding ``.git``, else ``start``.

    Found rather than computed because this file has two homes: the canonical repo's
    root, and a consumer's ``planning/`` — a fixed relative depth is wrong in one of them.
    """
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return start


def strip_fences(text: str) -> str:
    """Blank out fenced blocks, keeping line count, so code is never read as a heading."""
    out, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            out.append("")
            continue
        out.append("" if fenced else line)
    return "\n".join(out)


def link_lines(text: str) -> list[str]:
    """Lines with fenced blocks and inline spans removed — what to scan for real links.

    Only link scanning strips inline spans. A page documenting the markup an author should
    copy is not linking anywhere, while a heading's backticked content is part of its slug.
    """
    return [INLINE_CODE.sub("", line) for line in strip_fences(text).splitlines()]


def slugify(heading: str) -> str:
    """GitHub's heading slug: drop formatting and punctuation, lowercase, spaces to hyphens."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # `*` and `~` are emphasis; `_` is kept because GitHub keeps it and headings name
    # identifiers (`bound_type`) far more often than they use underscore-italics.
    text = re.sub(r"[*~]", "", text)
    text = "".join(ch for ch in text.lower() if ch.isalnum() or ch in " -_")
    return text.strip().replace(" ", "-")


def anchors(text: str) -> set[str]:
    """Every anchor a reader can target, including GitHub's ``-1``/``-2`` duplicate suffixes."""
    seen: collections.Counter[str] = collections.Counter()
    found: set[str] = set()
    for line in strip_fences(text).splitlines():
        match = HEADING.match(line)
        if not match:
            continue
        base = slugify(match.group(2))
        found.add(base if not seen[base] else f"{base}-{seen[base]}")
        seen[base] += 1
    return found


def check(root: pathlib.Path) -> list[str]:
    """Return one message per broken link; empty means every internal link resolves."""
    files = sorted(p for p in root.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(root).parts))
    cache: dict[pathlib.Path, set[str]] = {}
    violations: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(link_lines(text), 1):
            for target in LINK.findall(line):
                if EXTERNAL.match(target):
                    continue
                rel, _, fragment = target.partition("#")
                # A bare `#frag` targets this same file — the anchor is still checkable,
                # and a same-page link rots exactly like a cross-page one.
                dest = (path.parent / rel).resolve() if rel else path
                where = f"{path.relative_to(root)}:{line_no}"
                if not dest.exists():
                    violations.append(f"{where}: no such file -> {rel}")
                    continue
                if not fragment or dest.suffix != ".md":
                    continue
                if dest not in cache:
                    cache[dest] = anchors(dest.read_text(encoding="utf-8"))
                if fragment.lower() not in cache[dest]:
                    violations.append(f"{where}: no such anchor -> {target}")
    return violations


def main(argv: list[str] | None = None, root: pathlib.Path | None = None) -> int:
    """Report every broken link; return 1 if any, else 0."""
    parser = argparse.ArgumentParser(description="Check Markdown links and heading anchors.")
    parser.add_argument("--root", type=pathlib.Path, default=None)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    target = args.root or root or repo_root(pathlib.Path(__file__).resolve().parent)
    violations = check(target)
    if violations:
        sys.stderr.write(f"links: {len(violations)} broken\n")
        for violation in violations:
            sys.stderr.write(f"  - {violation}\n")
        return 1
    sys.stdout.write("links: OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
