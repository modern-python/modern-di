import dataclasses
import typing

from modern_di import errors
from modern_di.scope import Scope


@dataclasses.dataclass(frozen=True, slots=True)
class ResolutionStep:
    scope: Scope
    name: str


class ModernDIError(RuntimeError):
    """Base class for all modern-di errors. Inherits from RuntimeError for backwards compatibility."""


class ContainerError(ModernDIError):
    """Base class for container and scope errors."""


class InvalidChildScopeError(ContainerError):
    def __init__(self, *, parent_scope: Scope, child_scope: Scope, allowed_scopes: list[str]) -> None:
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
    def __init__(self, *, parent_scope: Scope) -> None:
        self.parent_scope = parent_scope
        super().__init__(errors.CONTAINER_MAX_SCOPE_REACHED_ERROR.format(parent_scope=parent_scope.name))


class ScopeNotInitializedError(ContainerError):
    def __init__(self, *, provider_scope: Scope, container_scope: Scope) -> None:
        self.provider_scope = provider_scope
        self.container_scope = container_scope
        super().__init__(
            errors.CONTAINER_NOT_INITIALIZED_SCOPE_ERROR.format(
                provider_scope=provider_scope.name,
                container_scope=container_scope.name,
            )
        )


class ScopeSkippedError(ContainerError):
    def __init__(self, *, provider_scope: Scope) -> None:
        self.provider_scope = provider_scope
        super().__init__(errors.CONTAINER_SCOPE_IS_SKIPPED_ERROR.format(provider_scope=provider_scope.name))


class ResolutionError(ModernDIError):
    """Base class for errors raised while resolving a provider.

    Carries an optional `dependency_path` accumulated as the error propagates up
    the resolution chain, so the rendered message shows the full path from the
    initially requested type down to the failing dependency.
    """

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
    def __init__(self, *, provider_type: type) -> None:
        self.provider_type = provider_type
        super().__init__(errors.CONTAINER_MISSING_PROVIDER_ERROR.format(provider_type=provider_type))


class ArgumentResolutionError(ResolutionError):
    def __init__(self, *, arg_name: str, arg_type: typing.Any, bound_type: typing.Any) -> None:  # noqa: ANN401
        self.arg_name = arg_name
        self.arg_type = arg_type
        self.bound_type = bound_type
        super().__init__(
            errors.FACTORY_ARGUMENT_RESOLUTION_ERROR.format(
                arg_name=arg_name,
                arg_type=arg_type,
                bound_type=bound_type,
            )
        )


class CircularDependencyError(ResolutionError):
    def __init__(self, *, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        super().__init__(errors.CYCLE_DEPENDENCY_ERROR.format(cycle_path=" -> ".join(cycle_path)))


class RegistrationError(ModernDIError):
    """Base class for errors raised while registering providers."""


class DuplicateProviderTypeError(RegistrationError):
    def __init__(self, *, provider_type: type) -> None:
        self.provider_type = provider_type
        super().__init__(errors.PROVIDER_DUPLICATE_TYPE_ERROR.format(provider_type=provider_type))


class FinalizerError(ModernDIError):
    def __init__(self, *, finalizer_errors: list[BaseException], is_async: bool) -> None:
        self.finalizer_errors = finalizer_errors
        self.is_async = is_async
        kind = "async" if is_async else "sync"
        super().__init__(f"Errors during {kind} cleanup: {finalizer_errors}")


class GroupInstantiationError(ModernDIError):
    def __init__(self, *, group_name: str) -> None:
        self.group_name = group_name
        super().__init__(f"{group_name} cannot be instantiated")
