import enum
import typing

from modern_di import types
from modern_di.providers.abstract import AbstractProvider


class ContextProvider(AbstractProvider[types.T_co]):
    """Provider for a runtime value passed as ``build_child_container(context={SomeType: value})``.

    The value is read from the context of the container at this provider's scope. With none set it resolves
    to ``default``. Without a ``default``, a direct resolve raises ``ContextValueNotSetError``. So
    does a ``Factory`` argument, unless its parameter is nullable or has a default: then the
    argument gets the parameter's default, or ``None``. ``default=None`` types the provider as
    ``ContextProvider[T | None]``.
    """

    __slots__ = ("_context_type", "_default")

    @typing.overload
    def __init__(
        self: "ContextProvider[types.T | None]",
        context_type: type[types.T],
        *,
        scope: enum.IntEnum | types.UnsetType = ...,
        bound_type: types.BoundType | types.UnsetType | None = ...,
        default: None,
    ) -> None: ...

    @typing.overload
    def __init__(
        self: "ContextProvider[types.T]",
        context_type: type[types.T],
        *,
        scope: enum.IntEnum | types.UnsetType = ...,
        bound_type: types.BoundType | types.UnsetType | None = ...,
        default: types.T | types.UnsetType = ...,
    ) -> None: ...

    def __init__(
        self,
        context_type: type[typing.Any],
        *,
        scope: enum.IntEnum | types.UnsetType = types.UNSET,
        bound_type: types.BoundType | types.UnsetType | None = types.UNSET,
        default: typing.Any = types.UNSET,
    ) -> None:
        super().__init__(scope=scope, bound_type=bound_type, inferred_bound_type=context_type)
        self._context_type = context_type
        self._default = default

    @property
    def context_type(self) -> type[types.T_co]:
        """The key this provider reads from the container's context."""
        return self._context_type

    @property
    def default(self) -> types.T_co | types.UnsetType:
        """The value resolved when no context value is set; ``UNSET`` when there is none."""
        return self._default

    def __repr__(self) -> str:
        return f"ContextProvider(context_type={self.context_type!r}, scope={self.scope!r})"
