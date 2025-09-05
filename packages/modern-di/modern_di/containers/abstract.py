import abc
import enum
import typing

from modern_di.provider_state import ProviderState
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    import typing_extensions


T_co = typing.TypeVar("T_co", covariant=True)


class AbstractContainer(abc.ABC):
    BASE_SLOTS: typing.ClassVar = (
        "_is_entered",
        "_overrides",
        "_provider_states",
        "_lock_factory",
        "context",
        "parent_container",
        "scope",
    )
    LOCK_FACTORY: type[typing.Any]

    def __init__(
        self,
        *,
        scope: enum.IntEnum = Scope.APP,
        parent_container: typing.Optional["typing_extensions.Self"] = None,
        context: dict[str, typing.Any] | None = None,
    ) -> None:
        self.scope = scope
        self.parent_container = parent_container
        self.context: dict[str, typing.Any] = context or {}
        self._is_entered: bool = False
        self._provider_states: dict[str, ProviderState[typing.Any]] = {}
        self._overrides: dict[str, typing.Any] = parent_container._overrides if parent_container else {}  # noqa: SLF001

    def _clear_state(self) -> None:
        self._is_entered = False
        self._provider_states = {}
        self._overrides = {}
        self.context = {}

    def _check_entered(self) -> None:
        if not self._is_entered:
            msg = f"Enter the context of {self.scope.name} scope"
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
            container = container.parent_container

        if container.scope != scope:
            msg = f"Scope {scope.name} is skipped"
            raise RuntimeError(msg)

        return container

    def fetch_provider_state(self, provider: AbstractProvider[T_co]) -> ProviderState[T_co] | None:
        if not provider.HAS_STATE:
            return None

        if provider_state := self._provider_states.get(provider.provider_id):
            return provider_state

        # expected to be thread-safe, because setdefault is atomic
        return self._provider_states.setdefault(provider.provider_id, ProviderState(lock_factory=self.LOCK_FACTORY))

    def override(self, provider: AbstractProvider[T_co], override_object: object) -> None:
        self._overrides[provider.provider_id] = override_object

    def reset_override(self, provider: AbstractProvider[T_co] | None = None) -> None:
        if provider is None:
            self._overrides = {}
        else:
            self._overrides.pop(provider.provider_id, None)

    def fetch_override(self, provider_id: str) -> object | None:
        return self._overrides.get(provider_id)

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Hack to prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Hack to prevent cloning object."""
        return self
