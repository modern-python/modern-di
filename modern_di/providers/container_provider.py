import typing

from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


class _ContainerProvider(AbstractProvider[typing.Any]):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(scope=Scope.APP, bound_type=None)


container_provider = _ContainerProvider()
