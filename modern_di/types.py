import typing


T_co = typing.TypeVar("T_co", covariant=True)
T = typing.TypeVar("T")
P = typing.ParamSpec("P")


class UnsetType:
    """Sentinel type separating 'not passed' from 'explicitly None'.

    :data:`UNSET` is the canonical instance; detect it with ``value is UNSET``.
    """

    def __repr__(self) -> str:
        return "UNSET"


UNSET: typing.Final[UnsetType] = UnsetType()
