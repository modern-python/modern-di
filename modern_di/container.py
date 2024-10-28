import contextlib
import enum
import types
import typing

from modern_di.resolver_state import ResolverState


if typing.TYPE_CHECKING:
    import typing_extensions


T_co = typing.TypeVar("T_co", covariant=True)


class Container(contextlib.AbstractAsyncContextManager["Container"]):
    __slots__ = "scope", "parent_container", "is_async", "_resolver_states"

    def __init__(self, *, scope: enum.IntEnum, parent_container: typing.Optional["Container"] = None) -> None:
        if scope.value != 1 and parent_container is not None:
            msg = "Only first scope can be used without parent_container"
            raise RuntimeError(msg)

        self.scope = scope
        self.parent_container = parent_container
        self.is_async: bool | None = None
        self._resolver_states: dict[str, ResolverState[typing.Any]] = {}

    def _exit(self) -> None:
        self.is_async = None
        self._resolver_states = {}

    def _check_entered(self) -> None:
        if self.is_async is None:
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

    def fetch_resolver_state(self, resolver_id: str, is_async: bool, is_resource: bool) -> ResolverState[typing.Any]:
        self._check_entered()
        if is_async and is_resource and self.is_async is False:
            msg = "Resolving async resource in sync container is not allowed"
            raise RuntimeError(msg)

        if resolver_id not in self._resolver_states:
            self._resolver_states[resolver_id] = ResolverState(is_async)

        return self._resolver_states[resolver_id]

    async def __aenter__(self) -> "Container":
        self.is_async = True
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
        self.is_async = False
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
