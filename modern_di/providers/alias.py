import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider


class Alias(AbstractProvider[types.T_co]):
    """Provider that resolves through whichever provider is registered for ``source_type``.

    Register it under ``bound_type``, typically an abstract base or ``Protocol``, to make that type
    resolve to an existing implementation, or pass ``bound_type=None`` to resolve it by reference only.
    A ``bound_type`` equal to ``source_type``, the default, raises ``AliasBoundToSourceError``. An alias
    holds no instance and has no scope of its own: caching and scope come from the source provider. The
    alias and its source can be overridden independently.
    """

    __slots__ = ("_source_type",)

    _takes_group_scope = False

    def __init__(
        self,
        source_type: type[types.T_co],
        *,
        bound_type: typing.Any = types.UNSET,  # noqa: ANN401
    ) -> None:
        super().__init__(scope=types.UNSET, bound_type=bound_type, inferred_bound_type=source_type)
        if self._bound_type == source_type:
            raise exceptions.AliasBoundToSourceError(source_type=source_type)
        self._source_type = source_type

    def __repr__(self) -> str:
        return f"Alias(source_type={self._source_type!r}, bound_type={self.bound_type!r}, scope={self.scope!r})"
