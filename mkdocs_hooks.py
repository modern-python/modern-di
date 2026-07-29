"""MkDocs build hooks.

Expands the `Changelog` nav placeholder into one entry per release page, so a new
release needs no `mkdocs.yml` edit. Registered via `hooks:` in `mkdocs.yml`.
"""

import pathlib
from typing import Any


_CHANGELOG_DIR = pathlib.Path(__file__).parent / "docs" / "changelog"
_PLACEHOLDER = "changelog/"


def version_key(path: pathlib.Path) -> tuple[int, ...]:
    """Sort key for a `<major>.<minor>.<patch>.md` release page."""
    return tuple(int(part) for part in path.stem.split("."))


def changelog_nav() -> list[Any]:
    """Build the Changelog section: the overview page, then every release newest-first."""
    pages = sorted((p for p in _CHANGELOG_DIR.glob("*.md") if p.stem != "index"), key=version_key, reverse=True)
    return [{"Overview": "changelog/index.md"}, *({p.stem: f"changelog/{p.name}"} for p in pages)]


def on_config(config: Any, **_kwargs: Any) -> Any:  # noqa: ANN401  # MkDocs passes its own Config type
    """Replace the `Changelog: changelog/` placeholder with the generated section."""
    for entry in config["nav"]:
        if isinstance(entry, dict) and entry.get("Changelog") == _PLACEHOLDER:
            entry["Changelog"] = changelog_nav()
            break
    return config
