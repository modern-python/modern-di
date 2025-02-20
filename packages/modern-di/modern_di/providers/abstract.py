import abc
import enum
import itertools
import typing
import uuid

from typing_extensions import override

from modern_di import Container
from modern_di.helpers.attr_getter_helpers import get_value_from_object_by_dotted_path


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

    def _sync_resolve_args(self, container: Container) -> list[typing.Any]:
        return [x.sync_resolve(container) if isinstance(x, AbstractProvider) else x for x in self._args]

    def _sync_resolve_kwargs(self, container: Container) -> dict[str, typing.Any]:
        return {k: v.sync_resolve(container) if isinstance(v, AbstractProvider) else v for k, v in self._kwargs.items()}

    def _sync_build_creator(self, container: Container) -> typing.Any:  # noqa: ANN401
        return self._creator(
            *self._sync_resolve_args(container),
            **self._sync_resolve_kwargs(container),
        )

    async def _async_resolve_args(self, container: Container) -> list[typing.Any]:
        return [await x.async_resolve(container) if isinstance(x, AbstractProvider) else x for x in self._args]

    async def _async_resolve_kwargs(self, container: Container) -> dict[str, typing.Any]:
        return {
            k: await v.async_resolve(container) if isinstance(v, AbstractProvider) else v
            for k, v in self._kwargs.items()
        }

    async def _async_build_creator(self, container: Container) -> typing.Any:  # noqa: ANN401
        return self._creator(
            *await self._async_resolve_args(container),
            **await self._async_resolve_kwargs(container),
        )


class AttrGetter(AbstractProvider[T_co]):
    """Provides an attribute after resolving the wrapped provider."""

    __slots__ = [*AbstractProvider.BASE_SLOTS, "_attrs", "_provider"]

    def __init__(self, provider: AbstractProvider[T_co], attr_name: str) -> None:
        """Create a new AttrGetter instance.

        Args:
            provider: provider to wrap.
            attr_name: attribute name to resolve when the provider is resolved.

        """
        super().__init__(scope=provider.scope)
        self._provider = provider
        self._attrs = [attr_name]

    def __getattr__(self, attr: str) -> "AttrGetter[T_co]":
        if attr.startswith("_"):
            msg = f"'{type(self)}' object has no attribute '{attr}'"
            raise AttributeError(msg)
        self._attrs.append(attr)
        return self

    @override
    async def async_resolve(self, container: Container) -> typing.Any:
        resolved_provider_object = await self._provider.async_resolve(container)
        attribute_path = ".".join(self._attrs)
        return get_value_from_object_by_dotted_path(resolved_provider_object, attribute_path)

    @override
    def sync_resolve(self, container: Container) -> typing.Any:
        resolved_provider_object = self._provider.sync_resolve(container)
        attribute_path = ".".join(self._attrs)
        return get_value_from_object_by_dotted_path(resolved_provider_object, attribute_path)
