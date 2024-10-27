import abc
import enum
import typing
import uuid

from modern_di.containers import AsyncContainer, SyncContainer


T_co = typing.TypeVar("T_co", covariant=True)
R = typing.TypeVar("R")
P = typing.ParamSpec("P")


class AbstractResolver(typing.Generic[T_co], abc.ABC):
    BASE_SLOTS: typing.Final = ["scope", "resolver_id", "_override"]

    def __init__(self, scope: enum.IntEnum) -> None:
        self.scope = scope
        self.resolver_id: typing.Final = str(uuid.uuid4())
        self._override: typing.Any = None

    @abc.abstractmethod
    async def async_resolve(self, container: AsyncContainer) -> T_co:
        """Resolve dependency asynchronously."""

    @abc.abstractmethod
    def sync_resolve(self, container: SyncContainer) -> T_co:
        """Resolve dependency synchronously."""

    def override(self, mock: object) -> None:
        self._override = mock

    def reset_override(self) -> None:
        self._override = None

    @property
    def cast(self) -> T_co:
        return typing.cast(T_co, self)
