import typing


T_co = typing.TypeVar("T_co", covariant=True)
T = typing.TypeVar("T")
P = typing.ParamSpec("P")


class UnsetType:
    """Sentinel type for parameters that distinguish 'not passed' from 'explicitly None'.

    The :data:`UNSET` module-level instance is the canonical sentinel. Use
    ``isinstance(value, UnsetType)`` or ``value is UNSET`` to detect it.
    """

    def __repr__(self) -> str:
        return "UNSET"


UNSET: typing.Final[UnsetType] = UnsetType()
