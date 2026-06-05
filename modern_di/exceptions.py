import dataclasses
import enum
import typing

from modern_di import errors


if typing.TYPE_CHECKING:
    from modern_di.providers.abstract import AbstractProvider


@dataclasses.dataclass(frozen=True, slots=True)
class ResolutionStep:
    scope: enum.IntEnum
    name: str


class ModernDIError(RuntimeError):
    """Base class for all modern-di errors. Inherits from RuntimeError for backwards compatibility."""

    __slots__ = ()


class ContainerError(ModernDIError):
    """Base class for container and scope errors."""

    __slots__ = ()


class InvalidChildScopeError(ContainerError):
    __slots__ = ("allowed_scopes", "child_scope", "parent_scope")

    def __init__(self, *, parent_scope: enum.IntEnum, child_scope: enum.IntEnum, allowed_scopes: list[str]) -> None:
        self.parent_scope = parent_scope
        self.child_scope = child_scope
        self.allowed_scopes = allowed_scopes
        super().__init__(
            errors.CONTAINER_SCOPE_IS_LOWER_ERROR.format(
                parent_scope=parent_scope.name,
                child_scope=child_scope.name,
                allowed_scopes=allowed_scopes,
            )
        )


class MaxScopeReachedError(ContainerError):
    __slots__ = ("parent_scope",)

    def __init__(self, *, parent_scope: enum.IntEnum) -> None:
        self.parent_scope = parent_scope
        super().__init__(errors.CONTAINER_MAX_SCOPE_REACHED_ERROR.format(parent_scope=parent_scope.name))


class ScopeNotInitializedError(ContainerError):
    __slots__ = ("container_scope", "provider_scope")

    def __init__(self, *, provider_scope: enum.IntEnum, container_scope: enum.IntEnum) -> None:
        self.provider_scope = provider_scope
        self.container_scope = container_scope
        super().__init__(
            errors.CONTAINER_NOT_INITIALIZED_SCOPE_ERROR.format(
                provider_scope=provider_scope.name,
                container_scope=container_scope.name,
            )
        )


class ScopeSkippedError(ContainerError):
    __slots__ = ("container_scope", "provider_scope")

    def __init__(self, *, provider_scope: enum.IntEnum, container_scope: enum.IntEnum) -> None:
        self.provider_scope = provider_scope
        self.container_scope = container_scope
        super().__init__(
            errors.CONTAINER_SCOPE_IS_SKIPPED_ERROR.format(
                provider_scope=provider_scope.name,
                container_scope=container_scope.name,
            )
        )


class InvalidScopeTypeError(ContainerError):
    __slots__ = ("scope_value",)

    def __init__(self, *, scope_value: typing.Any) -> None:  # noqa: ANN401
        self.scope_value = scope_value
        super().__init__(
            errors.INVALID_SCOPE_TYPE_ERROR.format(
                scope_repr=repr(scope_value),
                scope_type=type(scope_value).__name__,
            )
        )


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
    __slots__ = ("provider_type", "suggestions")

    def __init__(
        self,
        *,
        provider_type: type,
        suggestions: list[str] | None = None,
    ) -> None:
        self.provider_type = provider_type
        self.suggestions = suggestions or []
        message = errors.CONTAINER_MISSING_PROVIDER_ERROR.format(provider_type=provider_type)
        if self.suggestions:
            message += "\n" + errors.SUGGESTION_HEADER + "\n" + "\n".join(self.suggestions)
        super().__init__(message)


class AliasSourceNotRegisteredError(ResolutionError):
    __slots__ = ("source_type",)

    def __init__(self, *, source_type: type) -> None:
        self.source_type = source_type
        super().__init__(errors.ALIAS_SOURCE_NOT_REGISTERED_ERROR.format(source_type=source_type))


class ArgumentResolutionError(ResolutionError):
    __slots__ = ("arg_name", "arg_type", "bound_type", "suggestions")

    def __init__(
        self,
        *,
        arg_name: str,
        arg_type: typing.Any,  # noqa: ANN401
        bound_type: typing.Any,  # noqa: ANN401
        suggestions: list[str] | None = None,
    ) -> None:
        self.arg_name = arg_name
        self.arg_type = arg_type
        self.bound_type = bound_type
        self.suggestions = suggestions or []
        message = errors.FACTORY_ARGUMENT_RESOLUTION_ERROR.format(
            arg_name=arg_name,
            arg_type=arg_type,
            bound_type=bound_type,
        )
        if self.suggestions:
            message += "\n" + errors.SUGGESTION_HEADER + "\n" + "\n".join(self.suggestions)
        super().__init__(message)


class CircularDependencyError(ResolutionError):
    __slots__ = ("cycle_path",)

    def __init__(self, *, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        super().__init__(errors.CYCLE_DEPENDENCY_ERROR.format(cycle_path=" -> ".join(cycle_path)))


class RegistrationError(ModernDIError):
    """Base class for errors raised while registering providers."""

    __slots__ = ()


class DuplicateProviderTypeError(RegistrationError):
    __slots__ = ("provider_type",)

    def __init__(self, *, provider_type: type) -> None:
        self.provider_type = provider_type
        super().__init__(errors.PROVIDER_DUPLICATE_TYPE_ERROR.format(provider_type=provider_type))


class InvalidScopeDependencyError(RegistrationError):
    __slots__ = ("dep_provider", "parameter_name", "provider")

    def __init__(
        self,
        *,
        provider: "AbstractProvider[typing.Any]",
        parameter_name: str,
        dep_provider: "AbstractProvider[typing.Any]",
    ) -> None:
        self.provider = provider
        self.parameter_name = parameter_name
        self.dep_provider = dep_provider
        provider_name = provider.bound_type.__name__ if provider.bound_type else repr(provider)
        dep_name = dep_provider.bound_type.__name__ if dep_provider.bound_type else repr(dep_provider)
        super().__init__(
            errors.INVALID_SCOPE_DEPENDENCY_ERROR.format(
                provider_name=provider_name,
                provider_scope=provider.scope.name,
                parameter_name=parameter_name,
                dep_name=dep_name,
                dep_scope=dep_provider.scope.name,
            )
        )


class ValidationFailedError(ContainerError):
    __slots__ = ("errors",)

    def __init__(self, *, errors: list[Exception]) -> None:
        self.errors = errors
        kinds = ", ".join(sorted({type(e).__name__ for e in errors}))
        super().__init__(f"Container.validate() found {len(errors)} issue(s): {kinds}")

    def __str__(self) -> str:
        header = super().__str__()
        rendered = "\n".join(f"  - {e}" for e in self.errors)
        return f"{header}\n{rendered}"


class FinalizerError(ModernDIError):
    __slots__ = ("finalizer_errors", "is_async")

    def __init__(self, *, finalizer_errors: list[BaseException], is_async: bool) -> None:
        self.finalizer_errors = finalizer_errors
        self.is_async = is_async
        kind = "async" if is_async else "sync"
        super().__init__(f"Errors during {kind} cleanup: {finalizer_errors}")


class AsyncFinalizerInSyncCloseError(ModernDIError):
    """Raised when ``close_sync`` encounters a cached resource with an async finalizer."""

    __slots__ = ("finalizer_type",)

    def __init__(self, *, finalizer_type: type) -> None:
        self.finalizer_type = finalizer_type
        super().__init__(
            f"Cannot run async finalizer for {finalizer_type.__name__} during sync close. "
            f"Use `await container.close_async()` (or `async with container:`) instead."
        )


class GroupInstantiationError(ModernDIError):
    __slots__ = ("group_name",)

    def __init__(self, *, group_name: str) -> None:
        self.group_name = group_name
        super().__init__(f"{group_name} cannot be instantiated")
