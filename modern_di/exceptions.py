import dataclasses
import enum
import typing

from modern_di import suggester
from modern_di.scope import _deeper_members


SUGGESTION_HEADER = "Did you mean:"
_TROUBLESHOOTING_BASE_URL = "https://modern-di.modern-python.org/troubleshooting"


if typing.TYPE_CHECKING:
    from modern_di.providers.abstract import AbstractProvider


@dataclasses.dataclass(frozen=True, slots=True)
class ResolutionStep:
    """One entry in a chain-shaped error: a provider, as this module needs to draw it.

    Used both for a :class:`ResolutionError`'s ``dependency_path`` and for a
    :class:`CircularDependencyError`'s cycle, so both render through ``_render_chain``.

    Attributes:
        scope: the scope of the provider at this step of the chain.
        name: the provider's display name (bound type or creator name).
        location: the provider's declaration site as ``module:line``, when known.

    """

    scope: enum.IntEnum
    name: str
    location: str | None = None


def _render_chain(steps: "list[ResolutionStep]") -> list[str]:
    """Draw a provider chain as an indented arrow tree, one line per step.

    The single home of the chain glyphs — used by every chain-shaped error, so a
    resolution path and a dependency cycle cannot drift apart in how they read.
    """
    scope_width = max(len(step.scope.name) for step in steps)
    lines = []
    for i, step in enumerate(steps):
        prefix = "" if i == 0 else "    " * (i - 1) + "└─> "
        label = f"{step.name} ({step.location})" if step.location else step.name
        lines.append(f"  {step.scope.name:<{scope_width}}  {prefix}{label}")
    return lines


def _render_suggestion_lines(suggestions: "list[suggester.Suggestion]") -> list[str]:
    """Draw each suggestion as a bullet. The single home of the suggestion glyphs."""
    lines = []
    for suggestion in suggestions:
        details = [x for x in (suggestion.reason, _scope_detail(suggestion.scope)) if x]
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"  - {suggestion.name}{suffix}")
    return lines


def _scope_detail(scope: enum.IntEnum | None) -> str | None:
    return None if scope is None else f"scope={scope.name}"


def _render_suggestions(suggestions: "list[suggester.Suggestion]") -> str:
    """Render the full ``Did you mean:`` block, or an empty string when there is nothing to suggest."""
    if not suggestions:
        return ""
    return "\n".join([SUGGESTION_HEADER, *_render_suggestion_lines(suggestions)])


class ModernDIError(RuntimeError):
    """Base class for all modern-di errors. Inherits from RuntimeError for backwards compatibility.

    ``docs_slug`` names this class's page under ``docs/troubleshooting/``; ``__str__`` appends it
    as a trailing ``See: <url>`` line, always the final line of the rendered message. Base classes
    (this one, :class:`ContainerError`, :class:`ResolutionError`, :class:`RegistrationError`) are
    never raised directly and keep ``docs_slug`` unset; every concrete subclass sets one (enforced
    by the census test in ``tests/test_docs_slug_census.py``).
    """

    docs_slug: typing.ClassVar[str | None] = None

    __slots__ = ()

    def _render_body(self) -> str:
        """Message body without the docs trailer. Subclasses with custom rendering override this, not `__str__`."""
        return RuntimeError.__str__(self)

    def __str__(self) -> str:
        body = self._render_body()
        if self.docs_slug is None:
            return body
        return f"{body}\nSee: {_TROUBLESHOOTING_BASE_URL}/{self.docs_slug}/"


class DependencyPathMixin:
    """Breadcrumb machinery shared by :class:`ResolutionError` and the runtime scope errors.

    Owns `prepend_step` and the chain-rendering `_render_body` (the body `ModernDIError.__str__`
    appends the docs trailer to), so any error raised inside a resolution frame can accumulate the
    chain of provider names as it propagates back up to the caller. With an empty `dependency_path`
    (the error never passed through a resolution frame) `_render_body` returns the base message
    unchanged.

    Empty `__slots__`: each concrete error declares the `_base_message`/`dependency_path` slots
    itself, avoiding the `TypeError: multiple bases have instance lay-out conflict` that a slotted
    mixin combined with an `Exception` subclass would otherwise raise.
    """

    __slots__ = ()

    def __init__(self, message: str) -> None:
        self._base_message = message
        self.dependency_path: list[ResolutionStep] = []
        # Mixin's own base is `object`; the real MRO (via ResolutionError/ContainerError ->
        # ModernDIError -> RuntimeError) accepts the arg at runtime.
        super().__init__(message)  # ty: ignore[too-many-positional-arguments]

    def prepend_step(self, step: ResolutionStep) -> None:
        self.dependency_path.insert(0, step)
        self.args = (str(self),)

    def _render_body(self) -> str:
        if not self.dependency_path:
            return self._base_message

        lines = [
            "Cannot resolve dependency chain:",
            *_render_chain(self.dependency_path),
            f"  caused by: {self._base_message}",
        ]
        return "\n".join(lines)


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
        self.allowed_scopes = [member.name for member in _deeper_members(parent_scope)]
        super().__init__(
            f"Scope of child container cannot be {child_scope.name} if parent scope is {parent_scope.name} "
            f"(child scope value must be strictly greater than parent scope value). "
            f"Possible scopes are {self.allowed_scopes}."
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


class ScopeNotInitializedError(DependencyPathMixin, ContainerError):
    """Provider's scope is deeper than any active container. Inspect ``.provider_scope``, ``.container_scope``.

    Carries a breadcrumb ``.dependency_path`` (see :class:`DependencyPathMixin`) so a captive
    runtime dependency names both the failing provider and the one that captured it.
    """

    docs_slug = "scope-not-initialized-error"

    __slots__ = ("_base_message", "container_scope", "dependency_path", "provider_scope")

    def __init__(self, *, provider_scope: enum.IntEnum, container_scope: enum.IntEnum) -> None:
        self.provider_scope = provider_scope
        self.container_scope = container_scope
        super().__init__(
            f"Provider of scope {provider_scope.name} cannot be resolved in container of scope {container_scope.name}."
        )


class ScopeSkippedError(DependencyPathMixin, ContainerError):
    """Provider's scope was skipped in the container chain. Attrs: ``provider_scope``, ``container_scope``.

    Carries a breadcrumb ``.dependency_path`` (see :class:`DependencyPathMixin`) so a captive
    runtime dependency names both the failing provider and the one that captured it.
    """

    docs_slug = "scope-skipped-error"

    __slots__ = ("_base_message", "container_scope", "dependency_path", "provider_scope")

    def __init__(self, *, provider_scope: enum.IntEnum, container_scope: enum.IntEnum) -> None:
        self.provider_scope = provider_scope
        self.container_scope = container_scope
        super().__init__(
            f"No {provider_scope.name}-scope container exists in this chain; "
            f"this chain starts at {container_scope.name}. "
            f"Build a {provider_scope.name}-scope container as the root."
        )


class InvalidScopeTypeError(ContainerError):
    """A non-``IntEnum`` value was passed as a scope. Inspect ``.scope_value``."""

    docs_slug = "invalid-scope-type-error"

    __slots__ = ("scope_value",)

    def __init__(self, *, scope_value: typing.Any) -> None:  # noqa: ANN401
        self.scope_value = scope_value
        super().__init__(f"Scope must be an enum.IntEnum member; got {scope_value!r} ({type(scope_value).__name__}).")


class ContainerClosedError(ContainerError):
    """Operation attempted on a container that is not open. Attr: ``container_scope``.

    Covers both a never-opened container and one closed after use — a container
    must be entered (``with``/``async with``/:meth:`~modern_di.Container.open`)
    before it can resolve or build child containers.
    """

    docs_slug = "container-closed-error"

    __slots__ = ("container_scope",)

    def __init__(self, *, container_scope: enum.IntEnum) -> None:
        self.container_scope = container_scope
        super().__init__(
            f"Container (scope {container_scope.name}) is not open — enter it with `with`/`async with` "
            "or call `open()` before resolving or building child containers."
        )


class ContainerClosedWarning(DeprecationWarning):
    """Retained for back-compat of existing ``filterwarnings`` configs; no longer emitted.

    In modern-di 2.x this warned on reuse of a closed container, which then self-reopened. As of
    3.0 that reuse raises :class:`ContainerClosedError` instead, so this warning is never raised —
    the class stays importable so an existing::

        warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)

    does not break at import time.
    """


class UnvalidatedContainerWarning(FutureWarning):
    """Retained for back-compat of existing ``filterwarnings`` configs; no longer emitted.

    In modern-di 2.x this warned when a root container was built without an explicit ``validate``
    argument. As of 3.0, ``validate`` defaults to ``True`` and runs at container entry
    (:meth:`Container.open`/``with``), so there is nothing left to warn about — the class stays
    importable so an existing::

        warnings.filterwarnings("error", category=exceptions.UnvalidatedContainerWarning)

    does not break at import time.
    """


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
        arg_type: typing.Any,  # noqa: ANN401
        bound_type: typing.Any,  # noqa: ANN401
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

    def __init__(self, *, creator: typing.Any, original_error: Exception) -> None:  # noqa: ANN401
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
        creator: typing.Any,  # noqa: ANN401
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


class ContextValueNoneWarning(DeprecationWarning):
    """Retained for back-compat of existing ``filterwarnings`` configs; no longer emitted.

    In modern-di 2.x this warned when a direct resolve of an unset ``ContextProvider`` returned
    ``None``. As of 3.0 that resolve raises :class:`ContextValueNotSetError` instead, so this
    warning is never raised — the class stays importable so an existing::

        warnings.filterwarnings("error", category=exceptions.ContextValueNoneWarning)

    does not break at import time.
    """


class RegistrationError(ModernDIError):
    """Base class for errors raised while registering providers."""

    __slots__ = ()


class DuplicateProviderTypeError(RegistrationError):
    """Two providers were registered for the same ``.provider_type``."""

    docs_slug = "duplicate-type-error"

    __slots__ = ("provider_type",)

    def __init__(self, *, provider_type: type) -> None:
        self.provider_type = provider_type
        super().__init__(
            f"Provider is duplicated by type {provider_type}. "
            "To resolve this issue:\n"
            "1. Set bound_type=None on one of the providers to make it unresolvable by type\n"
            "2. Explicitly pass dependencies via the kwargs parameter to avoid automatic resolution"
        )


class ChildContainerRegistrationError(RegistrationError):
    """``add_providers`` was called on a child container; registration is root-only. Inspect ``.scope``."""

    docs_slug = "child-container-registration-error"

    __slots__ = ("scope",)

    def __init__(self, *, scope: enum.IntEnum) -> None:
        self.scope = scope
        super().__init__(
            f"Container.add_providers can only be called on a root container: the providers "
            f"registry is shared tree-wide, so registering on a child container (scope {scope.name}) "
            "would mutate every container in the tree. Call add_providers on the root container instead."
        )


class GroupScopeConflictError(RegistrationError):
    """A scope-defaulted provider is shared by two groups with different default scopes.

    Inspect ``.provider_name``, ``.first_group``/``.first_scope``, ``.second_group``/``.second_scope``.
    """

    docs_slug = "group-scope-conflict-error"

    __slots__ = ("first_group", "first_scope", "provider_name", "second_group", "second_scope")

    def __init__(
        self,
        *,
        provider_name: str,
        first_group: str,
        first_scope: enum.IntEnum,
        second_group: str,
        second_scope: enum.IntEnum,
    ) -> None:
        self.provider_name = provider_name
        self.first_group = first_group
        self.first_scope = first_scope
        self.second_group = second_group
        self.second_scope = second_scope
        super().__init__(
            f"Provider {provider_name} is shared by groups with conflicting default scopes: "
            f"{first_group} (scope {first_scope.name}) and {second_group} (scope {second_scope.name}). "
            f"Set scope= explicitly on the provider, or align the group defaults."
        )


class UnknownFactoryKwargError(RegistrationError):
    """Factory kwargs had unknown keys. Attrs: ``creator``, ``unknown_keys``, ``known_keys``, ``suggestions``."""

    docs_slug = "unknown-factory-kwarg-error"

    __slots__ = ("creator", "known_keys", "suggestions", "unknown_keys")

    def __init__(
        self,
        *,
        creator: typing.Any,  # noqa: ANN401
        unknown_keys: list[str],
        known_keys: list[str],
    ) -> None:
        self.creator = creator
        self.unknown_keys = unknown_keys
        self.known_keys = known_keys
        # Derived, not handed over: matching the unknown keys against the known ones needs
        # nothing the error was not already given. A kwarg has no provider, so no scope.
        self.suggestions = [
            suggester.Suggestion(
                name=repr(key),
                reason=f"did you mean {matches[0]!r}?"
                if (matches := suggester.close_matches(key, known_keys, n=1))
                else None,
            )
            for key in unknown_keys
        ]
        creator_name = getattr(creator, "__name__", repr(creator))
        parts = [
            f"Factory kwargs contain unknown key(s) not in {creator_name} signature:",
            *_render_suggestion_lines(self.suggestions),
            f"Known parameters: {known_keys}",
        ]
        super().__init__("\n".join(parts))


class UnsupportedCreatorParameterError(RegistrationError):
    """A creator parameter cannot be wired by type. Inspect ``.creator``, ``.parameter_name``, ``.reason``."""

    docs_slug = "unsupported-creator-parameter-error"

    __slots__ = ("creator", "parameter_name", "reason")

    def __init__(self, *, creator: typing.Any, parameter_name: str, reason: str) -> None:  # noqa: ANN401
        self.creator = creator
        self.parameter_name = parameter_name
        self.reason = reason
        creator_name = getattr(creator, "__name__", repr(creator))
        super().__init__(f"Parameter {parameter_name!r} of {creator_name} cannot be injected: {reason}")


class InvalidScopeDependencyError(RegistrationError):
    """A provider depends on a deeper-scoped one. Inspect ``.provider``, ``.parameter_name``, ``.dep_provider``."""

    docs_slug = "scope-chain"

    __slots__ = ("dep_provider", "parameter_name", "provider")

    def __init__(
        self,
        *,
        provider: "AbstractProvider[typing.Any]",
        parameter_name: str,
        dep_provider: "AbstractProvider[typing.Any]",
        dep_scope: enum.IntEnum | None = None,
    ) -> None:
        self.provider = provider
        self.parameter_name = parameter_name
        self.dep_provider = dep_provider
        provider_name = provider.display_name
        dep_name = dep_provider.display_name
        super().__init__(
            f"Provider {provider_name} (scope {provider.scope.name}) declares parameter "
            f"{parameter_name!r} typed as a provider of {dep_name} at deeper scope "
            f"{(dep_scope or dep_provider.scope).name}. A provider cannot depend on a deeper-scoped provider."
        )


class ValidationFailedError(ContainerError):
    """``validate()`` found one or more issues. Inspect ``.errors`` (the list of underlying exceptions).

    Sub-errors render trailer-free inside the grouped report below (see ``_render_body``) — only
    this error's own docs trailer appears, as the report's final line. Repeating each sub-error's
    "See: ..." line would be noise (the same URL once per error of a given kind) and would break
    the "one trailer, always last line" rule.
    """

    docs_slug = "validation-failed-error"

    __slots__ = ("errors",)

    def __init__(self, *, errors: list[Exception]) -> None:
        self.errors = errors
        kinds = ", ".join(sorted({type(e).__name__ for e in errors}))
        super().__init__(f"Container.validate() found {len(errors)} issue(s): {kinds}")

    def _render_body(self) -> str:
        lines = [RuntimeError.__str__(self)]
        by_kind: dict[str, list[Exception]] = {}
        for error in self.errors:
            by_kind.setdefault(type(error).__name__, []).append(error)
        for kind in sorted(by_kind):
            errors = by_kind[kind]
            lines.append(f"\n{kind} ({len(errors)}):")
            for error in errors:
                rendered = error._render_body() if isinstance(error, ModernDIError) else str(error)  # noqa: SLF001
                first, *rest = rendered.splitlines() or [""]
                lines.append(f"  - {first}".rstrip())
                lines.extend(f"    {line}" for line in rest)
        return "\n".join(lines)


class FinalizerError(ModernDIError):
    """One or more finalizers raised during close. Inspect ``.finalizer_errors`` and ``.is_async``."""

    docs_slug = "finalizer-error"

    __slots__ = ("finalizer_errors", "is_async")

    def __init__(self, *, finalizer_errors: list[BaseException], is_async: bool) -> None:
        self.finalizer_errors = finalizer_errors
        self.is_async = is_async
        kind = "async" if is_async else "sync"
        super().__init__(f"Errors during {kind} cleanup: {finalizer_errors}")


class AsyncFinalizerInSyncCloseError(ModernDIError):
    """Raised when ``close_sync`` encounters a cached resource with an async finalizer."""

    docs_slug = "async-finalizer-in-sync-close-error"

    __slots__ = ("finalizer_type",)

    def __init__(self, *, finalizer_type: type) -> None:
        self.finalizer_type = finalizer_type
        super().__init__(
            f"Cannot run async finalizer for {finalizer_type.__name__} during sync close. "
            "Use `await container.close_async()` (or `async with container:`) instead."
        )


class GroupInstantiationError(ModernDIError):
    """A ``Group`` subclass was instantiated. Inspect ``.group_name``; groups are namespaces, never objects."""

    docs_slug = "group-instantiation-error"

    __slots__ = ("group_name",)

    def __init__(self, *, group_name: str) -> None:
        self.group_name = group_name
        super().__init__(f"{group_name} cannot be instantiated")
