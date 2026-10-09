"""Errors raised while resolving a provider."""

import enum
import typing

from modern_di import suggester
from modern_di.exceptions.base import DependencyPathMixin, ModernDIError
from modern_di.exceptions.rendering import ResolutionStep, render_chain, render_suggestions, type_name


class ResolutionError(DependencyPathMixin, ModernDIError):
    """Base class for errors raised while resolving a provider.

    Carries an optional `dependency_path` accumulated as the error propagates up
    the resolution chain, so the rendered message shows the full path from the
    initially requested type down to the failing dependency. See
    :class:`DependencyPathMixin` for the shared machinery.
    """

    __slots__ = ("_base_message", "dependency_path")


class ProviderNotRegisteredError(ResolutionError):
    """No provider registered for the requested type. Inspect ``.dependency_type`` and ``.suggestions``."""

    docs_slug = "missing-provider"

    __slots__ = ("dependency_type", "suggestions")

    def __init__(
        self,
        *,
        dependency_type: type,
        suggestions: "list[suggester.Suggestion] | None" = None,
    ) -> None:
        self.dependency_type = dependency_type
        self.suggestions = suggestions or []
        message = f"No provider is registered for {type_name(dependency_type)}."
        if block := render_suggestions(self.suggestions):
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
            f"Register a provider for {source_type} before the alias is resolved."
        )


class ArgumentResolutionError(ResolutionError):
    """Creator parameter could not be wired.

    Attrs: ``parameter_name``, ``parameter_type``, ``member_types`` (the union members when there is no
    single ``parameter_type``), ``bound_type`` (``None`` when the provider has none), ``creator``,
    ``suggestions``.
    """

    docs_slug = "argument-resolution-error"

    __slots__ = ("bound_type", "creator", "member_types", "parameter_name", "parameter_type", "suggestions")

    def __init__(  # noqa: PLR0913
        self,
        *,
        parameter_name: str,
        parameter_type: type | None,
        bound_type: type | None,
        creator: "typing.Callable[..., typing.Any]",
        suggestions: "list[suggester.Suggestion] | None" = None,
        member_types: list[type] | None = None,
    ) -> None:
        self.parameter_name = parameter_name
        self.parameter_type = parameter_type
        self.bound_type = bound_type
        self.creator = creator
        self.member_types = member_types or []
        self.suggestions = suggestions or []
        building = f"Trying to build dependency {creator if bound_type is None else bound_type}."
        if parameter_type is not None:
            message = f"Argument {parameter_name} of type {parameter_type} cannot be resolved. {building}"
        elif self.member_types:
            joined = " | ".join(getattr(t, "__name__", str(t)) for t in self.member_types)
            message = f"Argument {parameter_name} of type {joined} cannot be resolved. {building}"
        else:
            message = (
                f"Argument {parameter_name} has no usable type annotation, so it cannot be resolved by type. "
                f"Pass it via the kwargs parameter or add a type annotation. {building}"
            )
        if block := render_suggestions(self.suggestions):
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
    def _from_type_error(
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
        error._prepend_step(resolution_step())
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
        rendered = "\n".join(render_chain(steps))
        super().__init__(f"Circular dependency detected:\n{rendered}\nCheck your provider graph for unintended cycles.")

    def _prepend_step(self, *steps: ResolutionStep) -> None:
        """No-op: the canonical cycle set at construction already names every provider in the loop.

        An outer resolver frame that catches the error has nothing to add, and prepending its step would
        only repeat a node of the cycle.
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
    """A ``ContextProvider`` with no ``default=`` was resolved with no value set.

    Inspect ``.context_type``, ``.provider_scope`` (the provider's scope), and ``.parameter_name``: the
    ``Factory`` parameter it was resolved for, or None for a direct resolve.
    """

    docs_slug = "context-not-set"

    __slots__ = ("context_type", "parameter_name", "provider_scope")

    def __init__(self, *, context_type: type, provider_scope: enum.IntEnum, parameter_name: str | None = None) -> None:
        self.context_type = context_type
        self.provider_scope = provider_scope
        self.parameter_name = parameter_name
        super().__init__(self._render_message())

    def _render_message(self) -> str:
        needed_for = "" if self.parameter_name is None else f", needed for argument {self.parameter_name}"
        return (
            f"No context value is set for {self.context_type!r} (scope {self.provider_scope.name}){needed_for}. "
            "Pass context={...} to the container or call set_context(), or pass default= to the ContextProvider."
        )

    def _name_parameter(self, parameter_name: str) -> None:
        """Record the ``Factory`` parameter this value was resolved for and re-render the message."""
        self.parameter_name = parameter_name
        self._base_message = self._render_message()
        self.args = (str(self),)
