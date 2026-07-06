import dataclasses
import enum
import typing


SUGGESTION_HEADER = "Did you mean:"


if typing.TYPE_CHECKING:
    from modern_di.providers.abstract import AbstractProvider


@dataclasses.dataclass(frozen=True, slots=True)
class ResolutionStep:
    """One entry in a :class:`ResolutionError`'s ``dependency_path``.

    Attributes:
        scope: the scope of the provider at this step of the resolution chain.
        name: the provider's display name (bound type or creator name).

    """

    scope: enum.IntEnum
    name: str


class ModernDIError(RuntimeError):
    """Base class for all modern-di errors. Inherits from RuntimeError for backwards compatibility."""

    __slots__ = ()


class ContainerError(ModernDIError):
    """Base class for container and scope errors."""

    __slots__ = ()


class InvalidChildScopeError(ContainerError):
    """Child scope is not deeper than the parent. Inspect ``.parent_scope``, ``.child_scope``, ``.allowed_scopes``."""

    __slots__ = ("allowed_scopes", "child_scope", "parent_scope")

    def __init__(self, *, parent_scope: enum.IntEnum, child_scope: enum.IntEnum, allowed_scopes: list[str]) -> None:
        self.parent_scope = parent_scope
        self.child_scope = child_scope
        self.allowed_scopes = allowed_scopes
        super().__init__(
            f"Scope of child container cannot be {child_scope.name} if parent scope is {parent_scope.name} "
            f"(child scope value must be strictly greater than parent scope value). "
            f"Possible scopes are {allowed_scopes}."
        )


class MaxScopeReachedError(ContainerError):
    """No scope deeper than ``.parent_scope`` exists, so no child scope can be auto-derived."""

    __slots__ = ("parent_scope",)

    def __init__(self, *, parent_scope: enum.IntEnum) -> None:
        self.parent_scope = parent_scope
        super().__init__(
            f"Max scope of {parent_scope.name} is reached. "
            "To go deeper, build a child container with a custom IntEnum scope whose value is higher."
        )


class ScopeNotInitializedError(ContainerError):
    """Provider's scope is deeper than any active container. Inspect ``.provider_scope``, ``.container_scope``."""

    __slots__ = ("container_scope", "provider_scope")

    def __init__(self, *, provider_scope: enum.IntEnum, container_scope: enum.IntEnum) -> None:
        self.provider_scope = provider_scope
        self.container_scope = container_scope
        super().__init__(
            f"Provider of scope {provider_scope.name} cannot be resolved in container of scope {container_scope.name}."
        )


class ScopeSkippedError(ContainerError):
    """Provider's scope was skipped in the container chain. Attrs: ``provider_scope``, ``container_scope``."""

    __slots__ = ("container_scope", "provider_scope")

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

    __slots__ = ("scope_value",)

    def __init__(self, *, scope_value: typing.Any) -> None:  # noqa: ANN401
        self.scope_value = scope_value
        super().__init__(
            f"Container scope must be an enum.IntEnum member; got {scope_value!r} ({type(scope_value).__name__})."
        )


class ContainerClosedError(ContainerError):
    """Operation attempted on a closed container. Attr: ``container_scope``.

    Raised in modern-di 3.0; until then reuse emits :class:`ContainerClosedWarning`
    and self-reopens.
    """

    __slots__ = ("container_scope",)

    def __init__(self, *, container_scope: enum.IntEnum) -> None:
        self.container_scope = container_scope
        super().__init__(
            f"Container (scope {container_scope.name}) is closed and can no longer resolve dependencies "
            "or build child containers. Create a new container."
        )


class ContainerClosedWarning(DeprecationWarning):
    """Reuse of a closed container (resolve / build a child) — transitional.

    The reuse works today because the container self-reopens, but it will raise
    :class:`ContainerClosedError` in modern-di 3.0. Opt into strict behavior now
    by escalating this warning::

        warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)
    """


class UnvalidatedContainerWarning(FutureWarning):
    """A root container was built without an explicit ``validate`` argument — transitional.

    modern-di 3.0 runs :meth:`Container.validate` at root construction by
    default. Pass ``validate=True`` to adopt the 3.0 behavior now, or
    ``validate=False`` to keep validation off (also after 3.0). Opt into strict
    behavior early by escalating this warning::

        warnings.filterwarnings("error", category=exceptions.UnvalidatedContainerWarning)
    """


class ResolutionError(ModernDIError):
    """Base class for errors raised while resolving a provider.

    Carries an optional `dependency_path` accumulated as the error propagates up
    the resolution chain, so the rendered message shows the full path from the
    initially requested type down to the failing dependency.
    """

    __slots__ = ("_base_message", "dependency_path")

    def __init__(self, message: str) -> None:
        self._base_message = message
        self.dependency_path: list[ResolutionStep] = []
        super().__init__(message)

    def prepend_step(self, step: ResolutionStep) -> None:
        self.dependency_path.insert(0, step)
        self.args = (str(self),)

    def __str__(self) -> str:
        if not self.dependency_path:
            return self._base_message

        scope_width = max(len(step.scope.name) for step in self.dependency_path)
        lines = ["Cannot resolve dependency chain:"]
        for i, step in enumerate(self.dependency_path):
            prefix = "" if i == 0 else "    " * (i - 1) + "└─> "
            lines.append(f"  {step.scope.name:<{scope_width}}  {prefix}{step.name}")
        lines.append(f"  caused by: {self._base_message}")
        return "\n".join(lines)


class ProviderNotRegisteredError(ResolutionError):
    """No provider registered for the requested type. Inspect ``.provider_type`` and ``.suggestions``."""

    __slots__ = ("provider_type", "suggestions")

    def __init__(
        self,
        *,
        provider_type: type,
        suggestions: list[str] | None = None,
    ) -> None:
        self.provider_type = provider_type
        self.suggestions = suggestions or []
        message = f"Provider of type {provider_type} is not registered in providers registry."
        if self.suggestions:
            message += "\n" + SUGGESTION_HEADER + "\n" + "\n".join(self.suggestions)
        super().__init__(message)


class AliasSourceNotRegisteredError(ResolutionError):
    """An ``Alias`` points at a ``.source_type`` that has no registered provider."""

    __slots__ = ("source_type",)

    def __init__(self, *, source_type: type) -> None:
        self.source_type = source_type
        super().__init__(
            f"Alias source type {source_type} is not registered in providers registry. "
            f"Register a provider for {source_type} before defining the alias."
        )


class ArgumentResolutionError(ResolutionError):
    """Creator parameter could not be wired. Attrs: ``arg_name``, ``arg_type``, ``bound_type``, ``suggestions``."""

    __slots__ = ("arg_name", "arg_type", "bound_type", "suggestions")

    def __init__(
        self,
        *,
        arg_name: str,
        arg_type: typing.Any,  # noqa: ANN401
        bound_type: typing.Any,  # noqa: ANN401
        suggestions: list[str] | None = None,
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
        if self.suggestions:
            message += "\n" + SUGGESTION_HEADER + "\n" + "\n".join(self.suggestions)
        super().__init__(message)


class CreatorCallError(ResolutionError):
    """A creator's dependencies resolved but the creator itself raised. Inspect ``.creator`` and ``.original_error``."""

    __slots__ = ("creator", "original_error")

    def __init__(self, *, creator: typing.Any, original_error: Exception) -> None:  # noqa: ANN401
        self.creator = creator
        self.original_error = original_error
        creator_name = getattr(creator, "__name__", repr(creator))
        super().__init__(
            f"Failed to call creator {creator_name}: {original_error}. Check kwargs and skip_creator_parsing usage."
        )


class CircularDependencyError(ResolutionError):
    """A dependency cycle was detected by ``validate()``. Inspect ``.cycle_path`` (the loop as type names)."""

    __slots__ = ("cycle_path",)

    def __init__(self, *, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        rendered = "\n".join(
            f"  {'    ' * (i - 1)}└─> {name}" if i else f"  {name}" for i, name in enumerate(cycle_path)
        )
        super().__init__(f"Circular dependency detected:\n{rendered}\nCheck your provider graph for unintended cycles.")


class ContextValueNotSetError(ResolutionError):
    """An unset ``ContextProvider`` was resolved directly.

    Raised in modern-di 3.0; until then direct resolve emits
    :class:`ContextValueNoneWarning` and returns ``None``. Inspect
    ``.context_type``.
    """

    __slots__ = ("context_type",)

    def __init__(self, *, context_type: type, scope_name: str) -> None:
        self.context_type = context_type
        super().__init__(
            f"No context value is set for {context_type!r} (scope {scope_name}). "
            "Pass context={...} to the container or call set_context()."
        )


class ContextValueNoneWarning(DeprecationWarning):
    """Direct resolve of an unset ``ContextProvider`` returned ``None`` — transitional.

    The ``None`` return works today but modern-di 3.0 raises
    :class:`ContextValueNotSetError` here. Opt into strict behavior now by
    escalating this warning::

        warnings.filterwarnings("error", category=exceptions.ContextValueNoneWarning)
    """


class RegistrationError(ModernDIError):
    """Base class for errors raised while registering providers."""

    __slots__ = ()


class DuplicateProviderTypeError(RegistrationError):
    """Two providers were registered for the same ``.provider_type``."""

    __slots__ = ("provider_type",)

    def __init__(self, *, provider_type: type) -> None:
        self.provider_type = provider_type
        super().__init__(
            f"Provider is duplicated by type {provider_type}. "
            "To resolve this issue:\n"
            "1. Set bound_type=None on one of the providers to make it unresolvable by type\n"
            "2. Explicitly pass dependencies via the kwargs parameter to avoid automatic resolution\n"
            "See https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/ for more details"
        )


class UnknownFactoryKwargError(RegistrationError):
    """Factory kwargs had unknown keys. Attrs: ``creator``, ``unknown_keys``, ``known_keys``, ``suggestions``."""

    __slots__ = ("creator", "known_keys", "suggestions", "unknown_keys")

    def __init__(
        self,
        *,
        creator: typing.Any,  # noqa: ANN401
        unknown_keys: list[str],
        known_keys: list[str],
        suggestions: dict[str, str] | None = None,
    ) -> None:
        self.creator = creator
        self.unknown_keys = unknown_keys
        self.known_keys = known_keys
        self.suggestions = suggestions or {}
        creator_name = getattr(creator, "__name__", repr(creator))
        parts = [f"Factory kwargs contain unknown key(s) not in {creator_name} signature:"]
        for key in unknown_keys:
            sug = self.suggestions.get(key)
            line = f"  - {key!r}"
            if sug:
                line += f" (did you mean {sug!r}?)"
            parts.append(line)
        parts.append(f"Known parameters: {known_keys}")
        # message built dynamically; not templated
        super().__init__("\n".join(parts))


class UnsupportedCreatorParameterError(RegistrationError):
    """A creator parameter cannot be wired by type. Inspect ``.creator``, ``.parameter_name``, ``.reason``."""

    __slots__ = ("creator", "parameter_name", "reason")

    def __init__(self, *, creator: typing.Any, parameter_name: str, reason: str) -> None:  # noqa: ANN401
        self.creator = creator
        self.parameter_name = parameter_name
        self.reason = reason
        creator_name = getattr(creator, "__name__", repr(creator))
        super().__init__(f"Parameter {parameter_name!r} of {creator_name} cannot be injected: {reason}")


class InvalidScopeDependencyError(RegistrationError):
    """A provider depends on a deeper-scoped one. Inspect ``.provider``, ``.parameter_name``, ``.dep_provider``."""

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
    """``validate()`` found one or more issues. Inspect ``.errors`` (the list of underlying exceptions)."""

    __slots__ = ("errors",)

    def __init__(self, *, errors: list[Exception]) -> None:
        self.errors = errors
        kinds = ", ".join(sorted({type(e).__name__ for e in errors}))
        # message built dynamically; not templated
        super().__init__(f"Container.validate() found {len(errors)} issue(s): {kinds}")

    def __str__(self) -> str:
        lines = [super().__str__()]
        by_kind: dict[str, list[Exception]] = {}
        for error in self.errors:
            by_kind.setdefault(type(error).__name__, []).append(error)
        for kind in sorted(by_kind):
            errors = by_kind[kind]
            lines.append(f"\n{kind} ({len(errors)}):")
            for error in errors:
                first, *rest = str(error).splitlines() or [""]
                lines.append(f"  - {first}".rstrip())
                lines.extend(f"    {line}" for line in rest)
        return "\n".join(lines)


class FinalizerError(ModernDIError):
    """One or more finalizers raised during close. Inspect ``.finalizer_errors`` and ``.is_async``."""

    __slots__ = ("finalizer_errors", "is_async")

    def __init__(self, *, finalizer_errors: list[BaseException], is_async: bool) -> None:
        self.finalizer_errors = finalizer_errors
        self.is_async = is_async
        kind = "async" if is_async else "sync"
        # message built dynamically; not templated
        super().__init__(f"Errors during {kind} cleanup: {finalizer_errors}")


class AsyncFinalizerInSyncCloseError(ModernDIError):
    """Raised when ``close_sync`` encounters a cached resource with an async finalizer."""

    __slots__ = ("finalizer_type",)

    def __init__(self, *, finalizer_type: type) -> None:
        self.finalizer_type = finalizer_type
        super().__init__(
            f"Cannot run async finalizer for {finalizer_type.__name__} during sync close. "
            "Use `await container.close_async()` (or `async with container:`) instead."
        )


class GroupInstantiationError(ModernDIError):
    """A ``Group`` subclass was instantiated. Inspect ``.group_name``; groups are namespaces, never objects."""

    __slots__ = ("group_name",)

    def __init__(self, *, group_name: str) -> None:
        self.group_name = group_name
        super().__init__(f"{group_name} cannot be instantiated")
