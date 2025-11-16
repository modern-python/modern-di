import abc
import enum
import typing
import uuid

import typing_extensions

from modern_di.helpers.type_helpers import define_bound_type
from modern_di.registries.state_registry.state import ProviderState


T_co = typing.TypeVar("T_co", covariant=True)
R = typing.TypeVar("R")
P = typing.ParamSpec("P")


class AbstractProvider(abc.ABC, typing.Generic[T_co]):
    BASE_SLOTS: typing.ClassVar = ["scope", "provider_id", "args", "kwargs", "is_async", "bound_type"]
    HAS_STATE: bool = False

    def __init__(
        self,
        scope: enum.IntEnum,
        args: list[typing.Any] | None = None,
        kwargs: dict[str, typing.Any] | None = None,
        bound_type: type | None = None,
    ) -> None:
        self.scope = scope
        self.provider_id: typing.Final = str(uuid.uuid4())
        self.args = args
        self.kwargs = kwargs
        self.is_async = False
        self.bound_type = bound_type
        self._check_providers_scope()

    def bind_type(self, new_type: type) -> typing_extensions.Self:
        self.bound_type = new_type
        return self

    async def async_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        provider_state: ProviderState[T_co] | None,
    ) -> T_co:  # pragma: no cover
        """Resolve dependency asynchronously."""
        raise NotImplementedError

    def sync_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        provider_state: ProviderState[T_co] | None,
    ) -> T_co:  # pragma: no cover
        """Resolve dependency synchronously."""
        raise NotImplementedError

    @property
    def cast(self) -> T_co:
        return typing.cast(T_co, self)

    def _check_providers_scope(self) -> None:
        if self.args:
            for provider in self.args:
                if isinstance(provider, AbstractProvider) and provider.scope > self.scope:
                    msg = f"Scope of dependency is {provider.scope.name} and current scope is {self.scope.name}"
                    raise RuntimeError(msg)

        if self.kwargs:
            for name, provider in self.kwargs.items():
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
        super().__init__(scope, args=list(args), kwargs=kwargs, bound_type=define_bound_type(creator))
        self._creator: typing.Final = creator
