import enum
import typing

from modern_di.resolver_state import ResolverState


if typing.TYPE_CHECKING:
    import typing_extensions


T_co = typing.TypeVar("T_co", covariant=True)


class AbstractContainer:
    BASE_SLOTS: typing.Final = "scope", "parent_container", "_is_entered", "_factory_states"

    def __init__(self, *, scope: enum.IntEnum, parent_container: typing.Optional["AbstractContainer"] = None) -> None:
        if scope.value != 1 and parent_container is not None:
            msg = "Only first scope can be used without parent_container"
            raise RuntimeError(msg)

        self.scope = scope
        self.parent_container = parent_container
        self._is_entered = False
        self._factory_states: dict[str, ResolverState[typing.Any]] = {}

    def _enter(self) -> None:
        self._is_entered = True

    def _exit(self) -> None:
        self._is_entered = False
        self._factory_states = {}

    def _check_entered(self) -> None:
        if not self._is_entered:
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

    def fetch_resolver_state(self, resolver_id: str, is_async: bool) -> ResolverState[typing.Any]:
        self._check_entered()
        if resolver_id not in self._factory_states:
            self._factory_states[resolver_id] = ResolverState(is_async)

        return self._factory_states[resolver_id]
