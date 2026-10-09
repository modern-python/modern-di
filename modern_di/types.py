import sys
import typing


T_co = typing.TypeVar("T_co", covariant=True)
T_contra = typing.TypeVar("T_contra", contravariant=True)
T = typing.TypeVar("T")

if typing.TYPE_CHECKING:
    if sys.version_info >= (3, 12):
        BoundType: typing.TypeAlias = type | typing.NewType | typing.TypeAliasType
    else:
        BoundType: typing.TypeAlias = type | typing.NewType
else:
    BoundType = type | typing.NewType | typing.TypeAliasType if sys.version_info >= (3, 12) else type | typing.NewType


class UnsetType:
    """Sentinel type separating 'not passed' from 'explicitly None'.

    :data:`UNSET` is the canonical instance; detect it with ``value is UNSET``.
    """

    def __repr__(self) -> str:
        return "UNSET"


UNSET: typing.Final[UnsetType] = UnsetType()
