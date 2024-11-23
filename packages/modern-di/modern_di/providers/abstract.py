import abc
import enum
import itertools
import typing
import uuid

from modern_di import Container


T_co = typing.TypeVar("T_co", covariant=True)
R = typing.TypeVar("R")
P = typing.ParamSpec("P")


class AbstractProvider(typing.Generic[T_co], abc.ABC):
    BASE_SLOTS: typing.ClassVar = ["scope", "provider_id"]

    def __init__(self, scope: enum.IntEnum) -> None:
        self.scope = scope
        self.provider_id: typing.Final = str(uuid.uuid4())

    @abc.abstractmethod
    async def async_resolve(self, container: Container) -> T_co:
        """Resolve dependency asynchronously."""

    @abc.abstractmethod
    def sync_resolve(self, container: Container) -> T_co:
        """Resolve dependency synchronously."""

    @property
    def cast(self) -> T_co:
        return typing.cast(T_co, self)

    def _check_providers_scope(self, providers: typing.Iterable[typing.Any]) -> None:
        if any(x.scope > self.scope for x in providers if isinstance(x, AbstractProvider)):
            msg = "Scope of dependency cannot be more than scope of dependent"
            raise RuntimeError(msg)


class AbstractOverrideProvider(AbstractProvider[T_co], abc.ABC):
    def override(self, override_object: object, container: Container) -> None:
        container.override(self.provider_id, override_object)

    def reset_override(self, container: Container) -> None:
        container.reset_override(self.provider_id)


class AbstractCreatorProvider(AbstractOverrideProvider[T_co], abc.ABC):
    BASE_SLOTS: typing.ClassVar = [*AbstractProvider.BASE_SLOTS, "_args", "_kwargs", "_creator"]

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, typing.Any],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope)
        self._check_providers_scope(itertools.chain(args, kwargs.values()))
        self._creator: typing.Final = creator
        self._args: typing.Final = args
        self._kwargs: typing.Final = kwargs

    def _sync_build_creator(self, container: Container) -> typing.Any:  # noqa: ANN401
        return self._creator(
            *typing.cast(
                P.args, [x.sync_resolve(container) if isinstance(x, AbstractProvider) else x for x in self._args]
            ),
            **typing.cast(
                P.kwargs,
                {
                    k: v.sync_resolve(container) if isinstance(v, AbstractProvider) else v
                    for k, v in self._kwargs.items()
                },
            ),
        )

    async def _async_build_creator(self, container: Container) -> typing.Any:  # noqa: ANN401
        return self._creator(
            *typing.cast(
                P.args,
                [await x.async_resolve(container) if isinstance(x, AbstractProvider) else x for x in self._args],
            ),
            **typing.cast(
                P.kwargs,
                {
                    k: await v.async_resolve(container) if isinstance(v, AbstractProvider) else v
                    for k, v in self._kwargs.items()
                },
            ),
        )
