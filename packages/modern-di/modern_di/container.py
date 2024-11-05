import contextlib
import enum
import types
import typing

from modern_di.provider_state import ProviderState


if typing.TYPE_CHECKING:
    import typing_extensions


T_co = typing.TypeVar("T_co", covariant=True)


class Container(contextlib.AbstractAsyncContextManager["Container"]):
    __slots__ = "scope", "parent_container", "context", "_is_async", "_provider_states", "_overrides"

    def __init__(
        self,
        *,
        scope: enum.IntEnum,
        parent_container: typing.Optional["Container"] = None,
        context: dict[str, typing.Any] | None = None,
    ) -> None:
        self.scope = scope
        self.parent_container = parent_container
        self.context: dict[str, typing.Any] = context or {}
        self._is_async: bool | None = None
        self._provider_states: dict[str, ProviderState[typing.Any]] = {}
        self._overrides: dict[str, typing.Any] = {}

    def _exit(self) -> None:
        self._is_async = None
        self._provider_states = {}
        self._overrides = {}
        self.context = {}

    def _check_entered(self) -> None:
        if self._is_async is None:
            msg = "Enter the context first"
            raise RuntimeError(msg)

    def build_child_container(
        self, context: dict[str, typing.Any] | None = None, scope: enum.IntEnum | None = None
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

    def fetch_provider_state(
        self, provider_id: str, is_async_resource: bool = False, is_lock_required: bool = False
    ) -> ProviderState[typing.Any]:
        self._check_entered()
        if is_async_resource and self._is_async is False:
            msg = "Resolving async resource in sync container is not allowed"
            raise RuntimeError(msg)

        if provider_id not in self._provider_states:
            self._provider_states[provider_id] = ProviderState(is_lock_required=is_lock_required)

        return self._provider_states[provider_id]

    def override(self, provider_id: str, override_object: object) -> None:
        self._overrides[provider_id] = override_object

    def fetch_override(self, provider_id: str) -> object | None:
        return self._overrides.get(provider_id)

    def reset_override(self, provider_id: str | None = None) -> None:
        if provider_id is None:
            self._overrides = {}
        else:
            self._overrides.pop(provider_id, None)

    async def __aenter__(self) -> "Container":
        self._is_async = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self._check_entered()
        for provider_state in reversed(self._provider_states.values()):
            await provider_state.async_tear_down()
        self._exit()

    def __enter__(self) -> "Container":
        self._is_async = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self._check_entered()
        for provider_state in reversed(self._provider_states.values()):
            provider_state.sync_tear_down()
        self._exit()
