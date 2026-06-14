import dataclasses
import difflib
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
    __slots__ = ("_creator", "_kwargs", "_parsed_kwargs", "cache_settings")

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
            if kwargs:
                self._validate_kwargs_against_signature(creator, kwargs, parsed_kwargs)
            for param_name, item in parsed_kwargs.items():
                if item.raw_annotation is None or item.default is not types.UNSET or (kwargs and param_name in kwargs):
                    continue
                raise exceptions.UnsupportedCreatorParameterError(
                    creator=creator,
                    parameter_name=param_name,
                    reason=(
                        f"parameterized generic annotation {item.raw_annotation!r} cannot be resolved by type; "
                        f"pass the value via the kwargs parameter, give the parameter a default, "
                        f"or use skip_creator_parsing=True"
                    ),
                )
        self._parsed_kwargs = parsed_kwargs
        super().__init__(scope=scope, bound_type=parsed_type if isinstance(bound_type, types.UnsetType) else bound_type)
        self._creator = creator
        self.cache_settings = cache_settings
        self._kwargs = kwargs

    @staticmethod
    def _validate_kwargs_against_signature(
        creator: typing.Callable[..., typing.Any],
        kwargs: dict[str, typing.Any],
        parsed_kwargs: dict[str, SignatureItem],
    ) -> None:
        try:
            sig = inspect.signature(creator)
        except (ValueError, TypeError):
            return
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            return
        known = set(parsed_kwargs)
        unknown = sorted(set(kwargs) - known)
        if not unknown:
            return
        suggestions: dict[str, str] = {}
        for bad in unknown:
            matches = difflib.get_close_matches(bad, known, n=1)
            if matches:
                suggestions[bad] = matches[0]
        raise exceptions.UnknownFactoryKwargError(
            creator=creator,
            unknown_keys=unknown,
            known_keys=sorted(known),
            suggestions=suggestions,
        )

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

    def _argument_resolution_error(
        self, arg_name: str, item: SignatureItem, suggestions: list[str]
    ) -> exceptions.ArgumentResolutionError:
        return exceptions.ArgumentResolutionError(
            arg_name=arg_name,
            arg_type=item.arg_type,
            bound_type=self.bound_type or self._creator,
            suggestions=suggestions,
            member_types=item.args,
        )

    def _compile_kwargs(
        self, container: "Container"
    ) -> tuple[dict[str, "AbstractProvider[typing.Any]"], dict[str, typing.Any], dict[str, typing.Any]]:
        """Partition parameters into live providers, static values, and live context lookups.

        ``context_kwargs`` holds parameters backed by a ``ContextProvider``; their value is
        looked up on every resolve (so a late ``set_context`` is always picked up) and the
        value-absent decision (default / None / raise) is deferred to resolve time. A
        parameter with no registered provider is a static graph fact, decided once here.
        """
        provider_kwargs: dict[str, AbstractProvider[typing.Any]] = {}
        static_kwargs: dict[str, typing.Any] = {}
        context_kwargs: dict[str, typing.Any] = {}
        for k, v in self._parsed_kwargs.items():
            if self._kwargs and k in self._kwargs:
                continue  # supplied as a static kwarg below
            provider = self._find_dep_provider(container, v)
            if provider is not None:
                if isinstance(provider, ContextProvider):
                    context_kwargs[k] = (provider, v)
                else:
                    provider_kwargs[k] = provider
                continue

            if v.default is not types.UNSET:
                continue
            if v.is_nullable:
                static_kwargs[k] = None
                continue
            suggestions = container.providers_registry.build_suggestions(v.arg_type) if v.arg_type is not None else []
            raise self._argument_resolution_error(k, v, suggestions)

        if self._kwargs:
            for k, static_value in self._kwargs.items():
                if isinstance(static_value, AbstractProvider):
                    provider_kwargs[k] = static_value
                else:
                    static_kwargs[k] = static_value
        return provider_kwargs, static_kwargs, context_kwargs

    def _ensure_kwargs_cached(
        self, container: "Container", cache_item: "CacheItem"
    ) -> tuple[dict[str, "AbstractProvider[typing.Any]"], dict[str, typing.Any], dict[str, typing.Any]]:
        # Compilation runs outside the container lock (the lock guards only singleton creation).
        # Under the GIL this is safe: the buckets are a deterministic function of the fixed providers
        # registry, so concurrent compiles produce identical results and at worst recompute once.
        # (Free-threaded/nogil caveat tracked in planning/deferred.md.)
        if not cache_item.kwargs_compiled:
            provider_kwargs, static_kwargs, context_kwargs = self._compile_kwargs(container)
            cache_item.provider_kwargs = provider_kwargs
            cache_item.static_kwargs = static_kwargs
            cache_item.context_kwargs = context_kwargs
            cache_item.kwargs_compiled = True
        return cache_item.provider_kwargs, cache_item.static_kwargs, cache_item.context_kwargs

    def _resolve_context_value(
        self, container: "Container", arg_name: str, provider: ContextProvider[typing.Any], item: SignatureItem
    ) -> typing.Any:  # noqa: ANN401
        """Resolve a context-backed parameter live. Returns ``types.UNSET`` to omit the kwarg.

        Mirrors ``Container.resolve_provider``'s override handling, then reads the live context
        value; an absent value falls back to the creator default (omit), ``None`` (nullable),
        or raises ``ArgumentResolutionError`` (required).
        """
        if container.overrides_registry.overrides:
            override = container.overrides_registry.fetch_override(provider.provider_id)
            if override is not types.UNSET:
                return override
        value = provider._find_context_value(container)  # noqa: SLF001
        if value is not types.UNSET:
            return value
        if item.default is not types.UNSET:
            return types.UNSET
        if item.is_nullable:
            return None
        raise self._argument_resolution_error(arg_name, item, [])

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
            if v.is_nullable:
                continue
            suggestions = container.providers_registry.build_suggestions(v.arg_type) if v.arg_type is not None else []
            yield exceptions.ArgumentResolutionError(
                arg_name=k,
                arg_type=v.arg_type,
                bound_type=self.bound_type or self._creator,
                suggestions=suggestions,
                member_types=v.args,
            )

    def _call_creator(self, resolved_kwargs: dict[str, typing.Any]) -> types.T_co:
        try:
            return self._creator(**resolved_kwargs)
        except TypeError as exc:
            # Only argument-binding failures are a DI wiring problem (bad/missing kwargs); those
            # raise at the call site, before entering the creator, so the traceback has no inner
            # frame. A TypeError raised inside the creator body is the creator's own error and
            # must propagate unchanged (consistent with ValueError/RuntimeError creator-failure).
            if exc.__traceback__ is not None and exc.__traceback__.tb_next is not None:
                raise
            error = exceptions.CreatorCallError(creator=self._creator, original_error=exc)
            error.prepend_step(self._resolution_step())
            raise error from exc

    def _resolve_kwargs(self, container: "Container", cache_item: "CacheItem") -> dict[str, typing.Any]:
        provider_kwargs, static_kwargs, context_kwargs = self._ensure_kwargs_cached(container, cache_item)
        resolved_kwargs = dict(static_kwargs)
        for k, v in provider_kwargs.items():
            resolved_kwargs[k] = container.resolve_provider(v)
        for k, (context_provider, item) in context_kwargs.items():
            value = self._resolve_context_value(container, k, context_provider, item)
            if value is not types.UNSET:
                resolved_kwargs[k] = value
        return resolved_kwargs

    def resolve(self, container: "Container") -> types.T_co:
        container = container.find_container(self.scope)
        if container.closed:
            raise exceptions.ContainerClosedError(container_scope=container.scope)
        cache_item = container.cache_registry.fetch_cache_item(self)

        if self.cache_settings and cache_item.cache is not types.UNSET:
            return cache_item.cache

        try:
            resolved_kwargs = self._resolve_kwargs(container, cache_item)
        except exceptions.ResolutionError as exc:
            exc.prepend_step(self._resolution_step())
            raise

        if not self.cache_settings:
            return self._call_creator(resolved_kwargs)

        if container.lock:
            container.lock.acquire()

        try:
            if cache_item.cache is not types.UNSET:
                return cache_item.cache

            instance = self._call_creator(resolved_kwargs)
            cache_item.cache = instance
            container.cache_registry.mark_created(cache_item)
            return instance
        finally:
            if container.lock:
                container.lock.release()
