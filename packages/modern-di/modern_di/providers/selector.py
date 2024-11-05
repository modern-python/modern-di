import enum
import typing

from modern_di import Container
from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Selector(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_function", "_providers"]

    def __init__(
        self, scope: enum.IntEnum, function: typing.Callable[..., str], **providers: AbstractProvider[T_co]
    ) -> None:
        super().__init__(scope)
        self._check_providers_scope(providers.values())
        self._function: typing.Final = function
        self._providers: typing.Final = providers

    async def async_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        selected_key = self._function(**container.context)
        if selected_key not in self._providers:
            msg = f"No provider matches {selected_key}"
            raise RuntimeError(msg)

        return await self._providers[selected_key].async_resolve(container)

    def sync_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        selected_key = self._function(**container.context)
        if selected_key not in self._providers:
            msg = f"No provider matches {selected_key}"
            raise RuntimeError(msg)

        return self._providers[selected_key].sync_resolve(container)
