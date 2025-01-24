import enum
import typing

from modern_di import Container
from modern_di.providers.abstract import AbstractOverrideProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Object(AbstractOverrideProvider[T_co]):
    __slots__ = [*AbstractOverrideProvider.BASE_SLOTS, "_obj"]

    def __init__(self, scope: enum.IntEnum, obj: T_co) -> None:
        super().__init__(scope)
        self._obj: typing.Final = obj

    async def async_resolve(self, container: Container) -> T_co:
        return self.sync_resolve(container)

    def sync_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        if (override := container.fetch_override(self.provider_id)) is not None:
            return typing.cast(T_co, override)

        return self._obj
