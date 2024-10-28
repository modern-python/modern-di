import contextlib
import enum
import types
import typing

from modern_di.resolver_state import ResolverState


if typing.TYPE_CHECKING:
    import typing_extensions


T_co = typing.TypeVar("T_co", covariant=True)


class Container(contextlib.AbstractAsyncContextManager["Container"]):
    __slots__ = "scope", "parent_container", "_is_async", "_resolver_states", "_overrides"

    def __init__(self, *, scope: enum.IntEnum, parent_container: typing.Optional["Container"] = None) -> None:
        if scope.value != 1 and parent_container is None:
            msg = "Only first scope can be used without parent_container"
            raise RuntimeError(msg)

        self.scope = scope
        self.parent_container = parent_container
        self._is_async: bool | None = None
        self._resolver_states: dict[str, ResolverState[typing.Any]] = {}
        self._overrides: dict[str, typing.Any] = {}

    def _exit(self) -> None:
        self._is_async = None
        self._resolver_states = {}

    def _check_entered(self) -> None:
        if self._is_async is None:
            msg = "Enter the context first"
            raise RuntimeError(msg)

    def build_child_container(self) -> "typing_extensions.Self":
        self._check_entered()

        try:
            new_scope = self.scope.__class__(self.scope.value + 1)
        except ValueError as exc:
            msg = f"Max scope is reached, {self.scope.name}"
            raise RuntimeError(msg) from exc

        return self.__class__(scope=new_scope, parent_container=self)

    def find_container(self, scope: enum.IntEnum) -> "typing_extensions.Self":
        container = self
        while container.scope > scope and container.parent_container:
            container = typing.cast("typing_extensions.Self", container.parent_container)
        return container

    def fetch_resolver_state(
        self, resolver_id: str, is_async_resource: bool = False, is_lock_required: bool = False
    ) -> ResolverState[typing.Any]:
        self._check_entered()
        if is_async_resource and self._is_async is False:
            msg = "Resolving async resource in sync container is not allowed"
            raise RuntimeError(msg)

        if resolver_id not in self._resolver_states:
            self._resolver_states[resolver_id] = ResolverState(is_lock_required=is_lock_required)

        return self._resolver_states[resolver_id]

    def override(self, resolver_id: str, override_object: object) -> None:
        self._overrides[resolver_id] = override_object

    def fetch_override(self, resolver_id: str) -> object | None:
        return self._overrides.get(resolver_id)

    def reset_override(self, resolver_id: str | None = None) -> None:
        if resolver_id is None:
            self._overrides = {}
        else:
            self._overrides.pop(resolver_id, None)

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
        for resolver_state in reversed(self._resolver_states.values()):
            await resolver_state.async_tear_down()
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
        for resolver_state in reversed(self._resolver_states.values()):
            resolver_state.sync_tear_down()
        self._exit()
