"""Census of docs_slug coverage across modern_di.exceptions (ERR-4/DOC-6).

Every concrete `ModernDIError` subclass sets a unique `docs_slug`, and every slug has a
matching page under `docs/troubleshooting/<slug>.md` — the full completeness gate. See
planning/changes/2026-07-07.06-error-docs-registry.md.
"""

import pathlib

from modern_di import exceptions


_REPO_ROOT = pathlib.Path(__file__).parent.parent
_TROUBLESHOOTING_DIR = _REPO_ROOT / "docs" / "troubleshooting"

# The 5 pre-existing troubleshooting pages plus the 16 new ones this change adds.
_EXPECTED_CONCRETE_CLASS_COUNT = 21

_BASE_CLASSES = frozenset(
    {
        exceptions.ModernDIError,
        exceptions.ContainerError,
        exceptions.ResolutionError,
        exceptions.RegistrationError,
    }
)


def _concrete_error_classes() -> list[type[exceptions.ModernDIError]]:
    # Walking modern_di/exceptions.py covers every error class by repo convention: all of them live there.
    return [
        obj
        for obj in vars(exceptions).values()
        if isinstance(obj, type) and issubclass(obj, exceptions.ModernDIError) and obj not in _BASE_CLASSES
    ]


def test_every_concrete_error_has_a_unique_docs_slug() -> None:
    classes = _concrete_error_classes()
    assert classes, "the walk over modern_di.exceptions found no concrete ModernDIError subclasses"

    missing = sorted(cls.__name__ for cls in classes if not cls.docs_slug)
    assert not missing, f"classes missing docs_slug: {missing}"

    slugs = [cls.docs_slug for cls in classes]
    assert len(slugs) == len(set(slugs)), "docs_slug values must be unique across all concrete error classes"


def test_every_docs_slug_has_a_troubleshooting_page() -> None:
    missing = sorted(
        cls.docs_slug
        for cls in _concrete_error_classes()
        if cls.docs_slug and not (_TROUBLESHOOTING_DIR / f"{cls.docs_slug}.md").exists()
    )
    assert not missing, f"docs_slug values with no matching docs/troubleshooting/<slug>.md page: {missing}"


def test_base_classes_have_no_docs_slug() -> None:
    # Base classes are never raised directly and never get a troubleshooting page.
    for base in _BASE_CLASSES:
        assert base.docs_slug is None


def test_census_pins_the_concrete_class_count() -> None:
    # Guards against a class silently falling out of (or into) the walk above — if this count
    # changes, a class was added/removed and the slug table (and, eventually, its page) must
    # follow in the same change.
    assert len(_concrete_error_classes()) == _EXPECTED_CONCRETE_CLASS_COUNT
