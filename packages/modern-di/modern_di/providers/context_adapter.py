import enum
import typing

from modern_di import Container
from modern_di.providers import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class ContextAdapter(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_function"]

    def __init__(
        self,
        scope: enum.IntEnum,
        function: typing.Callable[..., T_co],
    ) -> None:
        super().__init__(scope)
        self._function = function

    async def async_resolve(self, container: Container) -> T_co:
        return self._function(**container.find_container(self.scope).context)

    def sync_resolve(self, container: Container) -> T_co:
        return self._function(**container.find_container(self.scope).context)
