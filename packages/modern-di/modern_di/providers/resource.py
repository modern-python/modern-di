import contextlib
import enum
import inspect
import typing

from modern_di.providers.abstract import AbstractCreatorProvider
from modern_di.registries.state_registry.state import ProviderState


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Resource(AbstractCreatorProvider[T_co]):
    __slots__ = AbstractCreatorProvider.BASE_SLOTS
    HAS_STATE = True

    def _is_creator_async(
        self,
        _: contextlib.AbstractContextManager[T_co] | contextlib.AbstractAsyncContextManager[T_co],
    ) -> typing.TypeGuard[contextlib.AbstractAsyncContextManager[T_co]]:
        return self.is_async

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[
            P,
            typing.Iterator[T_co]
            | typing.AsyncIterator[T_co]
            | typing.ContextManager[T_co]
            | typing.AsyncContextManager[T_co],
        ],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        new_creator: typing.Any
        if inspect.isasyncgenfunction(creator):
            is_async = True
            new_creator = contextlib.asynccontextmanager(creator)
        elif inspect.isgeneratorfunction(creator):
            is_async = False
            new_creator = contextlib.contextmanager(creator)
        elif isinstance(creator, type) and issubclass(creator, typing.AsyncContextManager):
            is_async = True
            new_creator = creator
        elif isinstance(creator, type) and issubclass(creator, typing.ContextManager):
            is_async = False
            new_creator = creator
        else:
            msg = "Unsupported resource type"
            raise TypeError(msg)

        super().__init__(scope, new_creator, *args, **kwargs)
        self.is_async = is_async

    async def async_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        provider_state: ProviderState[T_co] | None,
        **_: object,
    ) -> T_co:
        assert provider_state
        _intermediate_ = self._creator(*args, **kwargs)
        if self._is_creator_async(self._creator):  # type: ignore[arg-type]
            provider_state.context_stack = contextlib.AsyncExitStack()
            provider_state.instance = await provider_state.context_stack.enter_async_context(_intermediate_)
        else:
            provider_state.context_stack = contextlib.ExitStack()
            provider_state.instance = provider_state.context_stack.enter_context(_intermediate_)

        return typing.cast(T_co, provider_state.instance)

    def sync_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        provider_state: ProviderState[T_co] | None,
        **_: object,
    ) -> T_co:
        assert provider_state
        _intermediate_ = self._creator(*args, **kwargs)
        provider_state.context_stack = contextlib.ExitStack()
        provider_state.instance = provider_state.context_stack.enter_context(
            typing.cast(contextlib.AbstractContextManager[typing.Any], _intermediate_)
        )

        return typing.cast(T_co, provider_state.instance)
