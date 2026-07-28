# ruff: noqa: INP001  # planning/ is not a Python package (this file is vendored into consumers' planning/)
"""Check every relative Markdown link and heading anchor in the repository.

Run via ``just check-links``. Exists because ``mkdocs build --strict`` only sees
``docs/``: ``architecture/`` and ``planning/`` live outside ``docs_dir``, so a link
that rots there is invisible to CI and is read on GitHub instead. Anchors in
``architecture/`` broke three times in one week before this existed.

Slugs follow **GitHub's** algorithm, because every file here is read on GitHub —
including the ones mkdocs also publishes. That is stricter than the site build in
one place that matters: python-markdown drops an em dash and collapses the
surrounding whitespace to a single hyphen, while GitHub drops the dash and keeps
both spaces as two hyphens. A heading containing " — " therefore has two different
anchors depending on the renderer, and the fix is to avoid the dash in headings you
link to rather than to teach this checker both dialects.

External links (``http``, ``https``, ``mailto``) are not fetched; this checks the
repository's internal consistency only.
"""

import argparse
import collections
import pathlib
import re
import sys


SKIP_DIRS = frozenset({".git", ".venv", ".superpowers", "site", "node_modules", "__pycache__", ".ruff_cache"})
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"(`+).+?\1")  # any run of backticks delimits a span: `x`, ``a`b``
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# [text](target) — target stops at whitespace (a title) or the closing paren.
LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)


def strip_fences(text: str) -> str:
    """Blank out fenced blocks, keeping line count, so code is never read as a heading or link."""
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

    Inline spans matter as much as fences here: a page documenting the markup an author
    should copy (``Usage example: [examples/](./examples)``) is not linking anywhere. Heading
    extraction deliberately does NOT strip them, because a heading's backticked content is
    part of its slug.
    """
    return [INLINE_CODE.sub("", line) for line in strip_fences(text).splitlines()]


def slugify(heading: str) -> str:
    """GitHub's heading slug: strip formatting and punctuation, lowercase, spaces to hyphens."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)  # inline code keeps its content
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links keep their text
    # `*` and `~` are only ever emphasis here; `_` is left alone because GitHub keeps it in the
    # slug and this repo's headings are full of identifiers (`bound_type`, `container_provider`).
    text = re.sub(r"[*~]", "", text)
    text = "".join(ch for ch in text.lower() if ch.isalnum() or ch in " -_")
    return text.strip().replace(" ", "-")


def anchors(text: str) -> set[str]:
    """Every anchor a reader can target in this file, including GitHub's -1/-2 duplicate suffixes."""
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
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(link_lines(text), 1):
            for target in LINK.findall(line):
                if EXTERNAL.match(target):
                    continue
                rel, _, fragment = target.partition("#")
                dest = path if not rel else (path.parent / rel).resolve()
                where = f"{path.relative_to(root)}:{line_no}"
                if not dest.exists():
                    errors.append(f"{where}: no such file -> {rel}")
                    continue
                if not fragment or dest.suffix != ".md":
                    continue
                if dest not in cache:
                    cache[dest] = anchors(dest.read_text(encoding="utf-8"))
                if fragment.lower() not in cache[dest]:
                    errors.append(f"{where}: no such anchor -> {target}")
    return errors


def main() -> None:
    """Print every broken link and exit non-zero, or report the count checked."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent.parent)
    args = parser.parse_args()

    errors = check(args.root)
    for error in errors:
        print(error)  # noqa: T201
    if errors:
        print(f"\nlinks: {len(errors)} broken")  # noqa: T201
        sys.exit(1)
    print("links: OK")  # noqa: T201


if __name__ == "__main__":
    main()
