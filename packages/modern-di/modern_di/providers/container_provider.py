import typing

import modern_di
from modern_di import Container
from modern_di.providers import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class ContainerProvider(AbstractProvider[modern_di.Container]):
    __slots__ = AbstractProvider.BASE_SLOTS

    async def async_resolve(self, container: Container) -> modern_di.Container:
        return self.sync_resolve(container)

    def sync_resolve(self, container: Container) -> modern_di.Container:
        return container.find_container(self.scope)
