import enum
import threading
import typing

from typing_extensions import TypedDict

from modern_di.group import Group
from modern_di.providers import ContainerProvider
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.context_provider import ContextProvider
from modern_di.registries.context_registry import ContextRegistry
from modern_di.registries.overrides_registry import OverridesRegistry
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.registries.state_registry.state_registry import StateRegistry
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    import typing_extensions


T_co = typing.TypeVar("T_co", covariant=True)


class AbstractContainerInitKwargs(TypedDict, total=False):
    scope: Scope
    parent_container: typing.Optional["AbstractContainer"]
    context: dict[type[typing.Any], typing.Any] | None
    groups: list[type[Group]] | None
    use_sync_lock: bool


class AbstractContainer:
    BASE_SLOTS: typing.ClassVar[list[str]] = [
        "_is_entered",
        "_sync_lock",
        "scope",
        "parent_container",
        "state_registry",
        "context_registry",
        "providers_registry",
        "overrides_registry",
    ]

    def __init__(self, **kwargs: "typing_extensions.Unpack[AbstractContainerInitKwargs]") -> None:
        scope = kwargs.get("scope", Scope.APP)
        parent_container = kwargs.get("parent_container")
        context = kwargs.get("context")
        groups = kwargs.get("groups")
        use_sync_lock = kwargs.get("use_sync_lock", True)

        self._is_entered = False
        self._sync_lock = threading.Lock() if use_sync_lock else None
        self.scope = scope
        self.parent_container = parent_container
        self.state_registry = StateRegistry()
        self.context_registry = ContextRegistry(context=context or {})
        self.providers_registry: ProvidersRegistry
        self.overrides_registry: OverridesRegistry
        if parent_container:
            self.providers_registry = parent_container.providers_registry
            self.overrides_registry = parent_container.overrides_registry
        else:
            self.providers_registry = ProvidersRegistry()
            self.overrides_registry = OverridesRegistry()
        if groups:
            for one_group in groups:
                self.providers_registry.add_providers(**one_group.get_providers())

    def _check_entered(self) -> None:
        if not self._is_entered:
            msg = f"Enter the context of {self.scope.name} scope"
            raise RuntimeError(msg)

    def _resolve_context_provider(self, provider: ContextProvider[T_co]) -> T_co | None:
        return self.context_registry.find_context(provider.context_type)

    def build_child_container(
        self, context: dict[type[typing.Any], typing.Any] | None = None, scope: Scope | None = None
    ) -> "typing_extensions.Self":
        self._check_entered()
        if scope and scope <= self.scope:
            msg = "Scope of child container must be more than current scope"
            raise RuntimeError(msg)

        if not scope:
            try:
                scope = self.scope.__class__(self.scope.value + 1)
            except ValueError as exc:
                msg = f"Max scope is reached, {self.scope.name}"
                raise RuntimeError(msg) from exc

        return self.__class__(scope=scope, parent_container=self, context=context)

    def find_container(self, scope: enum.IntEnum) -> "typing_extensions.Self":
        container = self
        if container.scope < scope:
            msg = f"Scope {scope.name} is not initialized"
            raise RuntimeError(msg)

        while container.scope > scope and container.parent_container:
            container = typing.cast("typing_extensions.Self", container.parent_container)

        if container.scope != scope:
            msg = f"Scope {scope.name} is skipped"
            raise RuntimeError(msg)

        return container

    def override(self, provider: AbstractProvider[T_co], override_object: object) -> None:
        self.overrides_registry.override(provider.provider_id, override_object)

    def reset_override(self, provider: AbstractProvider[T_co] | None = None) -> None:
        self.overrides_registry.reset_override(provider.provider_id if provider else None)

    def _sync_resolve_args(self, args: list[typing.Any]) -> list[typing.Any]:
        return [self._sync_resolve_provider(x) if isinstance(x, AbstractProvider) else x for x in args]

    def _sync_resolve_kwargs(self, kwargs: dict[str, typing.Any]) -> dict[str, typing.Any]:
        return {k: self._sync_resolve_provider(v) if isinstance(v, AbstractProvider) else v for k, v in kwargs.items()}

    def _sync_resolve(self, dependency_type: type[T_co] | None = None, *, dependency_name: str | None = None) -> T_co:
        provider = self.providers_registry.find_provider(
            dependency_type=dependency_type, dependency_name=dependency_name
        )
        if not provider:
            msg = f"Provider is not found, {dependency_type=}, {dependency_name=}"
            raise RuntimeError(msg)

        return self._sync_resolve_provider(provider)

    def _sync_resolve_provider(self, provider: AbstractProvider[T_co]) -> T_co:
        self._check_entered()
        if provider.is_async:
            msg = f"{type(provider).__name__} cannot be resolved synchronously"
            raise RuntimeError(msg)

        container = self.find_container(provider.scope)
        if isinstance(provider, ContainerProvider):
            return typing.cast(T_co, container)

        if isinstance(provider, ContextProvider):
            return typing.cast(T_co, self._resolve_context_provider(provider))

        if (override := container.overrides_registry.fetch_override(provider.provider_id)) is not None:
            return typing.cast(T_co, override)

        provider_state = container.state_registry.fetch_provider_state(provider)
        if provider_state and provider_state.instance is not None:
            return provider_state.instance

        args = self._sync_resolve_args(provider.args or [])
        kwargs = self._sync_resolve_kwargs(provider.kwargs or {})

        if provider_state and self._sync_lock:
            self._sync_lock.acquire()
        try:
            if provider_state and provider_state.instance is not None:
                return provider_state.instance

            return provider.sync_resolve(
                args=args,
                kwargs=kwargs,
                provider_state=provider_state,
            )
        finally:
            if provider_state and self._sync_lock:
                self._sync_lock.release()

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Hack to prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Hack to prevent cloning object."""
        return self
