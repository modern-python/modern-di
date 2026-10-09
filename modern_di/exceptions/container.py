"""Container and scope errors."""

import collections
import enum
import typing
from collections.abc import Sequence

from modern_di._scope_algebra import deeper_members
from modern_di.exceptions.base import ModernDIError
from modern_di.exceptions.rendering import ResolutionStep
from modern_di.exceptions.resolution import ResolutionError


class ContainerError(ModernDIError):
    """Base class for container and scope errors."""

    __slots__ = ()


class InvalidChildScopeError(ContainerError):
    """Child scope is not deeper than the parent. Inspect ``.parent_scope``, ``.child_scope``, ``.allowed_scopes``."""

    docs_slug = "invalid-child-scope-error"

    __slots__ = ("allowed_scopes", "child_scope", "parent_scope")

    def __init__(self, *, parent_scope: enum.IntEnum, child_scope: enum.IntEnum) -> None:
        self.parent_scope = parent_scope
        self.child_scope = child_scope
        # Derived, not handed over: the allowed scopes are a pure function of the parent's
        # own enum class, so a raise site has nothing to add.
        self.allowed_scopes = deeper_members(parent_scope)
        super().__init__(
            f"Scope of child container cannot be {child_scope.name} if parent scope is {parent_scope.name} "
            f"(child scope value must be strictly greater than parent scope value). "
            f"Possible scopes are {[member.name for member in self.allowed_scopes]}."
        )


class MaxScopeReachedError(ContainerError):
    """No scope deeper than ``.parent_scope`` exists, so no child scope can be auto-derived."""

    docs_slug = "max-scope-reached-error"

    __slots__ = ("parent_scope",)

    def __init__(self, *, parent_scope: enum.IntEnum) -> None:
        self.parent_scope = parent_scope
        super().__init__(
            f"Max scope of {parent_scope.name} is reached. "
            "To go deeper, build a child container with a custom IntEnum scope whose value is higher."
        )


class ScopeNotInitializedError(ResolutionError, ContainerError):
    """Provider's scope is deeper than any active container. Inspect ``.provider_scope``, ``.container_scope``.

    Carries a breadcrumb ``.dependency_path`` (see :class:`ResolutionError`) so a captive
    runtime dependency names both the failing provider and the one that captured it.
    """

    docs_slug = "scope-not-initialized-error"

    __slots__ = ("container_scope", "provider_scope")

    def __init__(self, *, provider_scope: enum.IntEnum, container_scope: enum.IntEnum) -> None:
        self.provider_scope = provider_scope
        self.container_scope = container_scope
        super().__init__(
            f"Provider of scope {provider_scope.name} cannot be resolved in container of scope {container_scope.name}."
        )


class ScopeSkippedError(ResolutionError, ContainerError):
    """Provider's scope was skipped in the container chain.

    Attrs: ``provider_scope``, ``container_scope`` (the resolving container), ``root_scope`` (the
    root of its chain). Carries a breadcrumb ``.dependency_path`` (see :class:`ResolutionError`)
    so a captive runtime dependency names both the failing provider and the one that captured it.
    """

    docs_slug = "scope-skipped-error"

    __slots__ = ("container_scope", "provider_scope", "root_scope")

    def __init__(
        self, *, provider_scope: enum.IntEnum, container_scope: enum.IntEnum, root_scope: enum.IntEnum
    ) -> None:
        self.provider_scope = provider_scope
        self.container_scope = container_scope
        self.root_scope = root_scope
        missing = f"No {provider_scope.name}-scope container exists in this chain"
        if provider_scope <= root_scope:
            message = (
                f"{missing}, which starts at {root_scope.name}. "
                f"Build the root container at scope {provider_scope.name}."
            )
        else:
            message = (
                f"{missing}, which runs from {root_scope.name} to {container_scope.name}. "
                f"Add a container at scope {provider_scope.name} to the chain."
            )
        super().__init__(message)


class InvalidScopeTypeError(ContainerError):
    """A non-``IntEnum`` value was passed as a scope. Inspect ``.scope_value``."""

    docs_slug = "invalid-scope-type-error"

    __slots__ = ("scope_value",)

    def __init__(self, *, scope_value: object) -> None:
        self.scope_value = scope_value
        super().__init__(f"Scope must be an enum.IntEnum member; got {scope_value!r} ({type(scope_value).__name__}).")


class ContainerClosedError(ResolutionError, ContainerError):
    """A closed container was resolved from, directly or through a descendant. Attr: ``container_scope``.

    ``container_scope`` names the closed container, which is an ancestor when a child's resolve
    reaches back into its scope. :meth:`Container.open`, or re-entering it with ``with`` /
    ``async with``, reopens it.
    """

    docs_slug = "container-closed-error"

    __slots__ = ("container_scope",)

    def __init__(self, *, container_scope: enum.IntEnum) -> None:
        self.container_scope = container_scope
        super().__init__(
            f"Container (scope {container_scope.name}) is closed. Reopen it with `open()` or by re-entering "
            "`with`/`async with` before resolving from it or from any of its child containers."
        )

    def _prepend_step(self, *steps: ResolutionStep) -> None:
        """No-op: ``container_scope`` already names the closed container, so ``dependency_path`` stays empty."""


class ValidationFailedError(ContainerError, ExceptionGroup[Exception]):
    """``validate()`` found one or more issues.

    An ``ExceptionGroup``: ``.exceptions`` holds the underlying errors, so ``except*`` can catch them
    by type, and a traceback shows each of them below this error's one-line summary.
    """

    docs_slug = "validation-failed-error"

    __slots__ = ()

    def __new__(cls, *, exceptions: Sequence[Exception]) -> typing.Self:
        return ExceptionGroup.__new__(cls, _validation_message(exceptions), exceptions)

    def __init__(self, *, exceptions: Sequence[Exception]) -> None:
        super().__init__(self.message, exceptions)

    def _render_body(self) -> str:
        return self.message

    def derive(self, excs: Sequence[Exception]) -> "ValidationFailedError":
        return ValidationFailedError(exceptions=excs)


def _validation_message(errors: Sequence[Exception]) -> str:
    counts = collections.Counter(type(error).__name__ for error in errors)
    kinds = ", ".join(f"{kind} ({counts[kind]})" for kind in sorted(counts))
    return f"Container.validate() found {len(errors)} issue(s): {kinds}"
