import abc
import enum
import itertools
import typing
import uuid

from modern_di import Container


T_co = typing.TypeVar("T_co", covariant=True)
R = typing.TypeVar("R")
P = typing.ParamSpec("P")


class AbstractResolver(typing.Generic[T_co], abc.ABC):
    BASE_SLOTS: typing.ClassVar = ["scope", "resolver_id", "_override"]

    def __init__(self, scope: enum.IntEnum) -> None:
        self.scope = scope
        self.resolver_id: typing.Final = str(uuid.uuid4())
        self._override: typing.Any = None

    @abc.abstractmethod
    async def async_resolve(self, container: Container) -> T_co:
        """Resolve dependency asynchronously."""

    @abc.abstractmethod
    def sync_resolve(self, container: Container) -> T_co:
        """Resolve dependency synchronously."""

    def override(self, mock: object) -> None:
        self._override = mock

    def reset_override(self) -> None:
        self._override = None

    @property
    def cast(self) -> T_co:
        return typing.cast(T_co, self)


class BaseCreatorResolver(AbstractResolver[T_co]):
    BASE_SLOTS: typing.ClassVar = [*AbstractResolver.BASE_SLOTS, "_args", "_kwargs"]

    def __init__(
        self,
        scope: enum.IntEnum,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope)

        if any(x.scope > self.scope for x in itertools.chain(args, kwargs.values()) if isinstance(x, AbstractResolver)):
            msg = "Scope of dependency cannot be more than scope of dependent"
            raise RuntimeError(msg)

        self._args: typing.Final = args
        self._kwargs: typing.Final = kwargs

    @abc.abstractmethod
    async def async_resolve(self, container: Container) -> T_co:
        """Resolve dependency asynchronously."""

    @abc.abstractmethod
    def sync_resolve(self, container: Container) -> T_co:
        """Resolve dependency synchronously."""

    def override(self, mock: object) -> None:
        self._override = mock

    def reset_override(self) -> None:
        self._override = None

    @property
    def cast(self) -> T_co:
        return typing.cast(T_co, self)
