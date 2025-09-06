import abc
import enum
import typing
import uuid

import typing_extensions
from typing_extensions import override

from modern_di.helpers.attr_getter_helpers import get_value_from_object_by_dotted_path
from modern_di.helpers.type_helpers import define_bound_type
from modern_di.registries.state_registry.state import AsyncState, SyncState


T_co = typing.TypeVar("T_co", covariant=True)
R = typing.TypeVar("R")
P = typing.ParamSpec("P")


class AbstractProvider(typing.Generic[T_co], abc.ABC):
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
        self._args = args
        self._kwargs = kwargs
        self.is_async = False
        self.bound_type = bound_type
        self._check_providers_scope()

    def bind_type(self, new_type: type) -> typing_extensions.Self:
        self.bound_type = new_type
        return self

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
        provider_state: AsyncState[T_co] | None,
    ) -> T_co:  # pragma: no cover
        """Resolve dependency asynchronously."""
        raise NotImplementedError

    def sync_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        context: dict[str, typing.Any],
        provider_state: SyncState[T_co] | None,
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

    def __getattr__(self, attr_name: str) -> typing.Any:  # noqa: ANN401
        """Get an attribute from the resolve object.

        Args:
            attr_name: name of attribute to get.

        Returns:
            An `AttrGetter` provider that will get the attribute after resolving the current provider.

        """
        if attr_name.startswith("_"):
            msg = f"'{type(self)}' object has no attribute '{attr_name}'"
            raise AttributeError(msg)

        return AttrGetter(provider=self, attr_name=attr_name)


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


class AttrGetter(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_attrs"]

    def __init__(self, provider: AbstractProvider[T_co], attr_name: str) -> None:
        super().__init__(scope=provider.scope, args=[provider])
        self._attrs = [attr_name]

    def __getattr__(self, attr: str) -> "AttrGetter[T_co]":
        if attr.startswith("_"):
            msg = f"'{type(self)}' object has no attribute '{attr}'"
            raise AttributeError(msg)
        self._attrs.append(attr)
        return self

    @override
    async def async_resolve(
        self,
        *,
        args: list[typing.Any],
        **_: object,
    ) -> typing.Any:
        attribute_path = ".".join(self._attrs)
        return get_value_from_object_by_dotted_path(args[0], attribute_path)

    @override
    def sync_resolve(
        self,
        *,
        args: list[typing.Any],
        **_: object,
    ) -> typing.Any:
        attribute_path = ".".join(self._attrs)
        return get_value_from_object_by_dotted_path(args[0], attribute_path)
