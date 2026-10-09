import typing

from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


class _ContainerProvider(AbstractProvider[typing.Any]):
    __slots__ = ()

    _takes_group_scope = False
    _ignores_scope = True

    def __init__(self) -> None:
        super().__init__(scope=Scope.APP, bound_type=None)

    def __repr__(self) -> str:
        return "container_provider"

    @property
    def display_name(self) -> str:
        return "Container"


container_provider = _ContainerProvider()
