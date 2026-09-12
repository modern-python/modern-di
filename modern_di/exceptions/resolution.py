"""Errors raised while resolving a provider."""

import typing

from modern_di import suggester
from modern_di.exceptions.base import DependencyPathMixin, ModernDIError
from modern_di.exceptions.rendering import ResolutionStep, _render_chain, _render_suggestions


class ResolutionError(DependencyPathMixin, ModernDIError):
    """Base class for errors raised while resolving a provider.

    Carries an optional `dependency_path` accumulated as the error propagates up
    the resolution chain, so the rendered message shows the full path from the
    initially requested type down to the failing dependency. See
    :class:`DependencyPathMixin` for the shared machinery.
    """

    __slots__ = ("_base_message", "dependency_path")


class ProviderNotRegisteredError(ResolutionError):
    """No provider registered for the requested type. Inspect ``.provider_type`` and ``.suggestions``."""

    docs_slug = "missing-provider"

    __slots__ = ("provider_type", "suggestions")

    def __init__(
        self,
        *,
        provider_type: type,
        suggestions: "list[suggester.Suggestion] | None" = None,
    ) -> None:
        self.provider_type = provider_type
        self.suggestions = suggestions or []
        message = f"Provider of type {provider_type} is not registered in providers registry."
        if block := _render_suggestions(self.suggestions):
            message += "\n" + block
        super().__init__(message)


class AliasSourceNotRegisteredError(ResolutionError):
    """An ``Alias`` points at a ``.source_type`` that has no registered provider."""

    docs_slug = "alias-source-not-registered-error"

    __slots__ = ("source_type",)

    def __init__(self, *, source_type: type) -> None:
        self.source_type = source_type
        super().__init__(
            f"Alias source type {source_type} is not registered in providers registry. "
            f"Register a provider for {source_type} before defining the alias."
        )


class ArgumentResolutionError(ResolutionError):
    """Creator parameter could not be wired. Attrs: ``arg_name``, ``arg_type``, ``bound_type``, ``suggestions``."""

    docs_slug = "argument-resolution-error"

    __slots__ = ("arg_name", "arg_type", "bound_type", "suggestions")

    def __init__(
        self,
        *,
        arg_name: str,
        arg_type: type | None,
        bound_type: "type | typing.Callable[..., typing.Any]",
        suggestions: "list[suggester.Suggestion] | None" = None,
        member_types: list[type] | None = None,
    ) -> None:
        self.arg_name = arg_name
        self.arg_type = arg_type
        self.bound_type = bound_type
        self.suggestions = suggestions or []
        if arg_type is not None:
            message = (
                f"Argument {arg_name} of type {arg_type} cannot be resolved. Trying to build dependency {bound_type}."
            )
        elif member_types:
            joined = " | ".join(getattr(t, "__name__", str(t)) for t in member_types)
            message = (
                f"Argument {arg_name} of type {joined} cannot be resolved. Trying to build dependency {bound_type}."
            )
        else:
            message = (
                f"Argument {arg_name} has no usable type annotation, so it cannot be resolved by type. "
                f"Pass it via the kwargs parameter or add a type annotation. Trying to build dependency {bound_type}."
            )
        if block := _render_suggestions(self.suggestions):
            message += "\n" + block
        super().__init__(message)


class CreatorCallError(ResolutionError):
    """Argument binding failed when calling the creator (kwargs mismatch). Inspect ``.creator``, ``.original_error``."""

    docs_slug = "creator-call-error"

    __slots__ = ("creator", "original_error")

    def __init__(self, *, creator: "typing.Callable[..., typing.Any]", original_error: Exception) -> None:
        self.creator = creator
        self.original_error = original_error
        creator_name = getattr(creator, "__name__", repr(creator))
        super().__init__(
            f"Failed to call creator {creator_name}: {original_error}. Check kwargs and skip_creator_parsing usage."
        )

    @classmethod
    def from_type_error(
        cls,
        *,
        creator: "typing.Callable[..., typing.Any]",
        exc: TypeError,
        resolution_step: "typing.Callable[[], ResolutionStep]",
    ) -> "CreatorCallError | None":
        """Wrap an argument-binding ``TypeError`` as a ``CreatorCallError`` with the resolution step prepended.

        A ``TypeError`` raised *inside* the creator body (it carries an inner traceback frame) is not a
        binding failure: return ``None`` so the caller re-raises it unchanged. The resolution step is built
        only when wrapping, never on the propagate path.
        """
        if exc.__traceback__ is not None and exc.__traceback__.tb_next is not None:
            return None
        error = cls(creator=creator, original_error=exc)
        error.prepend_step(resolution_step())
        return error


class CircularDependencyError(ResolutionError):
    """A dependency cycle was detected by ``validate()`` or the runtime resolve guard.

    Inspect ``.steps`` (the loop, first provider repeated last), or the ``.cycle_path`` /
    ``.cycle_locations`` views derived from it. When raised at resolve time, ``__cause__``
    carries the original ``RecursionError``.
    """

    docs_slug = "circular-dependency"

    __slots__ = ("steps",)

    def __init__(self, *, steps: list[ResolutionStep]) -> None:
        self.steps = steps
        rendered = "\n".join(_render_chain(steps))
        super().__init__(f"Circular dependency detected:\n{rendered}\nCheck your provider graph for unintended cycles.")

    def prepend_step(self, step: ResolutionStep) -> None:
        """No-op: the canonical cycle (set at construction) is already self-contained.

        Every provider in the loop is named by ``steps``, so an outer resolution frame has nothing
        to add — accumulating a breadcrumb would only repeat the same nodes. This also keeps the two
        resolve paths identical: the interpreted path unwinds through intermediate ``resolve_provider``
        frames (each would otherwise prepend a step), while the compiled path converts once at the top.
        """

    @property
    def cycle_path(self) -> list[str]:
        """The cycle as provider names."""
        return [step.name for step in self.steps]

    @property
    def cycle_locations(self) -> list[str | None]:
        """The cycle's ``module:line`` anchors, positionally parallel to ``cycle_path``."""
        return [step.location for step in self.steps]


class ContextValueNotSetError(ResolutionError):
    """An unset ``ContextProvider`` was resolved directly. Inspect ``.context_type``."""

    docs_slug = "context-not-set"

    __slots__ = ("context_type",)

    def __init__(self, *, context_type: type, scope_name: str) -> None:
        self.context_type = context_type
        super().__init__(
            f"No context value is set for {context_type!r} (scope {scope_name}). "
            "Pass context={...} to the container or call set_context()."
        )
