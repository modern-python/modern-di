import typing

from modern_di.providers.abstract import AbstractCreatorProvider
from modern_di.scope import Scope


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")
SyncFinalizerType = typing.Callable[[T_co], None]
AsyncFinalizerType = typing.Callable[[T_co], typing.Coroutine[None, None, None]]


class Singleton(AbstractCreatorProvider[T_co]):
    __slots__ = AbstractCreatorProvider.BASE_SLOTS

    def __init__(
        self,
        scope: Scope,
        creator: typing.Callable[P, T_co],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope, creator, *args, **kwargs)
