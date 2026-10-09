import typing

from modern_di import types
from modern_di.providers.abstract import AbstractProvider


class Alias(AbstractProvider[types.T_co]):
    __slots__ = ("_source_type",)

    _takes_group_scope = False

    def __init__(
        self,
        source_type: type[types.T_co],
        *,
        bound_type: typing.Any = types.UNSET,  # noqa: ANN401
    ) -> None:
        super().__init__(scope=types.UNSET, bound_type=bound_type, inferred_bound_type=source_type)
        self._source_type = source_type

    def __repr__(self) -> str:
        return f"Alias(source_type={self._source_type!r}, bound_type={self.bound_type!r}, scope={self.scope!r})"
