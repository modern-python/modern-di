import dataclasses
import inspect
import typing

from modern_di import types
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope
from modern_di.types_parser import parse_creator


if typing.TYPE_CHECKING:
    from modern_di import Container


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheSettings(typing.Generic[types.T_co]):
    clear_cache: bool = True
    finalizer: typing.Callable[[types.T_co], None | typing.Awaitable[None]] | None = None
    is_async_finalizer: bool = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.is_async_finalizer = bool(self.finalizer) and inspect.iscoroutinefunction(self.finalizer)


class Factory(AbstractProvider[types.T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_creator", "_kwargs", "_parsed_kwargs", "cache_settings"]

    def __init__(
        self,
        *,
        scope: Scope = Scope.APP,
        creator: typing.Callable[..., types.T_co],
        bound_type: type | None = types.UNSET,  # type: ignore[assignment]
        kwargs: dict[str, typing.Any] | None = None,
        cache_settings: CacheSettings[types.T_co] | None = None,
    ) -> None:
        dependency_type, self._parsed_kwargs = parse_creator(creator)
        super().__init__(scope=scope, bound_type=bound_type if bound_type != types.UNSET else dependency_type.arg_type)
        self._creator = creator
        self.cache_settings = cache_settings
        self._kwargs = kwargs

    def _compile_kwargs(self, container: "Container") -> dict[str, typing.Any]:
        result: dict[str, typing.Any] = {}
        for k, v in self._parsed_kwargs.items():
            provider: AbstractProvider[types.T_co] | None = container.providers_registry.find_provider(
                dependency_name=k, dependency_type=v.arg_type
            )
            if provider:
                result[k] = provider
                continue

            if (not self._kwargs or k not in self._kwargs) and v.default == types.UNSET:
                msg = f"Argument {k} cannot be resolved, type={v.arg_type}"
                raise RuntimeError(msg)

        if self._kwargs:
            result.update(self._kwargs)
        return result

    def resolve(self, container: "Container") -> types.T_co:
        container = container.find_container(self.scope)
        cache_item = container.cache_registry.fetch_cache_item(self)
        if cache_item.kwargs is not None:
            kwargs = cache_item.kwargs
        else:
            kwargs = self._compile_kwargs(container)
            cache_item.kwargs = kwargs

        resolved_kwargs = {k: v.resolve(container) if isinstance(v, AbstractProvider) else v for k, v in kwargs.items()}

        if not self.cache_settings:
            return self._creator(**resolved_kwargs)

        if cache_item.cache is not None:
            return typing.cast(types.T_co, cache_item.cache)

        if container.lock:
            container.lock.acquire()

        try:
            if cache_item.cache is not None:
                return typing.cast(types.T_co, cache_item.cache)

            instance = self._creator(**resolved_kwargs)
            cache_item.cache = instance
            return instance
        finally:
            if container.lock:
                container.lock.release()
