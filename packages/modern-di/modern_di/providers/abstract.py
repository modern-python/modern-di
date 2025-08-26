import abc
import enum
import typing
import uuid

from modern_di.provider_state import ProviderState


T_co = typing.TypeVar("T_co", covariant=True)
R = typing.TypeVar("R")
P = typing.ParamSpec("P")


class AbstractProvider(typing.Generic[T_co], abc.ABC):
    BASE_SLOTS: typing.ClassVar = ["scope", "provider_id", "args", "kwargs", "is_async"]
    HAS_STATE: bool = False

    def __init__(
        self,
        scope: enum.IntEnum,
        args: list[typing.Any] | None = None,
        kwargs: dict[str, typing.Any] | None = None,
    ) -> None:
        self.scope = scope
        self.provider_id: typing.Final = str(uuid.uuid4())
        self._args = args
        self._kwargs = kwargs
        self.is_async = False
        self._check_providers_scope()

    def fetch_args(self, _: dict[str, typing.Any]) -> list[typing.Any]:
        return self._args or []

    def fetch_kwargs(self, _: dict[str, typing.Any]) -> dict[str, typing.Any]:
        return self._kwargs or {}

    async def async_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        context: dict[str, typing.Any],
        provider_state: ProviderState[T_co] | None,
    ) -> T_co:  # pragma: no cover
        """Resolve dependency asynchronously."""
        raise NotImplementedError

    def sync_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        context: dict[str, typing.Any],
        provider_state: ProviderState[T_co] | None,
    ) -> T_co:  # pragma: no cover
        """Resolve dependency synchronously."""
        raise NotImplementedError

    @property
    def cast(self) -> T_co:
        return typing.cast(T_co, self)

    def _check_providers_scope(self) -> None:
        if self._args:
            for provider in self._args:
                if isinstance(provider, AbstractProvider) and provider.scope > self.scope:
                    msg = f"Scope of dependency is {provider.scope.name} and current scope is {self.scope.name}"
                    raise RuntimeError(msg)

        if self._kwargs:
            for name, provider in self._kwargs.items():
                if isinstance(provider, AbstractProvider) and provider.scope > self.scope:
                    msg = f"Scope of {name} is {provider.scope.name} and current scope is {self.scope.name}"
                    raise RuntimeError(msg)


class AbstractCreatorProvider(AbstractProvider[T_co], abc.ABC):
    BASE_SLOTS: typing.ClassVar = [*AbstractProvider.BASE_SLOTS, "_creator"]

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, typing.Any],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope, args=list(args), kwargs=kwargs)
        self._creator: typing.Final = creator
