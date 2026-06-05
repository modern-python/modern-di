import dataclasses
import enum
import inspect
import typing
import warnings

from modern_di import exceptions, types
from modern_di.providers import ContextProvider
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope
from modern_di.types_parser import SignatureItem, parse_creator


if typing.TYPE_CHECKING:
    from modern_di import Container
    from modern_di.registries.cache_registry import CacheItem


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheSettings(typing.Generic[types.T_co]):
    clear_cache: bool = True
    finalizer: typing.Callable[[types.T_co], None | typing.Awaitable[None]] | None = None
    is_async_finalizer: bool = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.is_async_finalizer = bool(self.finalizer) and inspect.iscoroutinefunction(self.finalizer)


class Factory(AbstractProvider[types.T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_creator", "_kwargs", "_parsed_kwargs", "cache_settings"]

    def __init__(  # noqa: PLR0913
        self,
        *,
        scope: enum.IntEnum = Scope.APP,
        creator: typing.Callable[..., types.T_co],
        bound_type: type | None | types.UnsetType = types.UNSET,
        kwargs: dict[str, typing.Any] | None = None,
        cache_settings: CacheSettings[types.T_co] | None = None,
        skip_creator_parsing: bool = False,
    ) -> None:
        if skip_creator_parsing:
            if bound_type is types.UNSET:
                warnings.warn(
                    "skip_creator_parsing=True without an explicit bound_type means this provider "
                    "cannot be resolved by type. Pass bound_type=MyClass if you need type resolution.",
                    UserWarning,
                    stacklevel=2,
                )
            parsed_type: type | None = None
            parsed_kwargs: dict[str, SignatureItem] = {}
        else:
            return_sig, parsed_kwargs = parse_creator(creator)
            parsed_type = return_sig.arg_type
        self._parsed_kwargs = parsed_kwargs
        super().__init__(scope=scope, bound_type=parsed_type if isinstance(bound_type, types.UnsetType) else bound_type)
        self._creator = creator
        self.cache_settings = cache_settings
        self._kwargs = kwargs

    def __repr__(self) -> str:
        return f"Factory(creator={self._creator!r}, scope={self.scope!r}, cached={self.cache_settings is not None})"

    def _resolution_step(self) -> exceptions.ResolutionStep:
        name = self.bound_type.__name__ if self.bound_type else getattr(self._creator, "__name__", repr(self._creator))
        return exceptions.ResolutionStep(scope=self.scope, name=name)

    def _find_dep_provider(self, container: "Container", v: SignatureItem) -> "AbstractProvider[typing.Any] | None":
        if v.arg_type:
            provider = container.providers_registry.find_provider(v.arg_type)
            if provider is self:
                return None
            return provider
        for x in v.args:
            provider = container.providers_registry.find_provider(x)
            if provider is not None and provider is not self:
                return provider
        return None

    def _compile_kwargs(self, container: "Container") -> dict[str, typing.Any]:
        result: dict[str, typing.Any] = {}
        for k, v in self._parsed_kwargs.items():
            provider = self._find_dep_provider(container, v)
            is_kwarg_not_found = not self._kwargs or k not in self._kwargs
            if provider:
                result[k] = provider
                if (
                    is_kwarg_not_found
                    and isinstance(provider, ContextProvider)
                    and provider._find_context_value(container) is types.UNSET  # noqa: SLF001
                ):
                    raise exceptions.ArgumentResolutionError(
                        arg_name=k, arg_type=v.arg_type, bound_type=self.bound_type or self._creator
                    )
                continue

            if v.default == types.UNSET and is_kwarg_not_found:
                suggestions = (
                    container.providers_registry.build_suggestions(v.arg_type) if v.arg_type is not None else []
                )
                raise exceptions.ArgumentResolutionError(
                    arg_name=k,
                    arg_type=v.arg_type,
                    bound_type=self.bound_type or self._creator,
                    suggestions=suggestions,
                )

        if self._kwargs:
            result.update(self._kwargs)
        return result

    def _ensure_kwargs_cached(
        self, container: "Container", cache_item: "CacheItem"
    ) -> tuple[dict[str, "AbstractProvider[typing.Any]"], dict[str, typing.Any]]:
        if not cache_item.kwargs_compiled:
            kwargs = self._compile_kwargs(container)
            provider_kwargs: dict[str, AbstractProvider[typing.Any]] = {}
            static_kwargs: dict[str, typing.Any] = {}
            for k, v in kwargs.items():
                if isinstance(v, AbstractProvider):
                    provider_kwargs[k] = v
                else:
                    static_kwargs[k] = v
            cache_item.provider_kwargs = provider_kwargs
            cache_item.static_kwargs = static_kwargs
            cache_item.kwargs_compiled = True
        return cache_item.provider_kwargs, cache_item.static_kwargs

    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:
        """Return parameter-name → dependency-provider mapping using only the providers registry.

        Pure lookup: no scope check, no cache touch, no context-value lookup. Used by
        Container.validate() to traverse the static graph.
        """
        result: dict[str, AbstractProvider[typing.Any]] = {}
        for k, v in self._parsed_kwargs.items():
            if self._kwargs and k in self._kwargs:
                continue
            provider = self._find_dep_provider(container, v)
            if provider is not None:
                result[k] = provider
        return result

    def iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:
        """Yield ArgumentResolutionError for parameters with no provider, no default, no static kwarg."""
        for k, v in self._parsed_kwargs.items():
            is_kwarg_not_found = not self._kwargs or k not in self._kwargs
            if not is_kwarg_not_found:
                continue
            if self._find_dep_provider(container, v) is not None:
                continue
            if v.default is not types.UNSET:
                continue
            suggestions = container.providers_registry.build_suggestions(v.arg_type) if v.arg_type is not None else []
            yield exceptions.ArgumentResolutionError(
                arg_name=k,
                arg_type=v.arg_type,
                bound_type=self.bound_type or self._creator,
                suggestions=suggestions,
            )

    def resolve(self, container: "Container") -> types.T_co:
        container = container.find_container(self.scope)
        cache_item = container.cache_registry.fetch_cache_item(self)

        if self.cache_settings and cache_item.cache is not types.UNSET:
            return cache_item.cache

        try:
            provider_kwargs, static_kwargs = self._ensure_kwargs_cached(container, cache_item)
            resolved_kwargs = dict(static_kwargs)
            for k, v in provider_kwargs.items():
                resolved_kwargs[k] = container.resolve_provider(v)
        except exceptions.ResolutionError as exc:
            exc.prepend_step(self._resolution_step())
            raise

        if not self.cache_settings:
            return self._creator(**resolved_kwargs)

        if container.lock:
            container.lock.acquire()

        try:
            if cache_item.cache is not types.UNSET:
                return cache_item.cache

            instance = self._creator(**resolved_kwargs)
            cache_item.cache = instance
            return instance
        finally:
            if container.lock:
                container.lock.release()
