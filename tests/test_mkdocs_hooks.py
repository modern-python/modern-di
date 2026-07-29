"""The changelog nav hook: release pages are listed newest-first, numerically.

Guards the ordering trap a lexical sort would hit — 2.9.0 must follow 2.10.0, not precede it.
"""

import pathlib

import pytest

import mkdocs_hooks


def test_version_key_orders_numerically_not_lexically() -> None:
    ordered = sorted([pathlib.Path("2.10.0.md"), pathlib.Path("2.9.0.md")], key=mkdocs_hooks.version_key)
    assert [p.stem for p in ordered] == ["2.9.0", "2.10.0"]


def test_changelog_nav_starts_with_overview_then_newest_first() -> None:
    nav = mkdocs_hooks.changelog_nav()
    assert nav[0] == {"Overview": "changelog/index.md"}

    versions = [next(iter(entry)) for entry in nav[1:]]
    assert versions == sorted(versions, key=lambda v: tuple(int(p) for p in v.split(".")), reverse=True)
    assert "index" not in versions
    assert all(next(iter(entry.values())) == f"changelog/{next(iter(entry))}.md" for entry in nav[1:])


def test_on_config_expands_only_the_changelog_placeholder() -> None:
    config = {"nav": [{"Quick-Start": "index.md"}, {"Changelog": "changelog/"}, {"Development": [{"C": "c.md"}]}]}

    result = mkdocs_hooks.on_config(config)

    assert result is config
    assert result["nav"][0] == {"Quick-Start": "index.md"}
    assert result["nav"][2] == {"Development": [{"C": "c.md"}]}
    assert result["nav"][1]["Changelog"][0] == {"Overview": "changelog/index.md"}


@pytest.mark.parametrize("nav", [[{"Changelog": "elsewhere/"}], [{"Quick-Start": "index.md"}], ["changelog/"]])
def test_on_config_leaves_nav_untouched_without_the_placeholder(nav: list[object]) -> None:
    assert mkdocs_hooks.on_config({"nav": nav})["nav"] == nav
