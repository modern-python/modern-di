"""Compile one flat closure resolver per provider (the single resolve path).

Each resolver front-guards its own override, navigates its target once (same-scope deps skip
the navigation via an int compare), inlines the kwargs build and creator call, and calls its
dependencies' resolvers by reference. Behavior-sensitive helpers (`_resolution_step`,
`_resolve_context_value`, `prepend_step`) are reused, not reimplemented.
"""

import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.factory import Factory


if typing.TYPE_CHECKING:
    from modern_di import Container
    from modern_di.providers.context_provider import ContextProvider
    from modern_di.registries.providers_registry import ProvidersRegistry
    from modern_di.types_parser import SignatureItem

    _ProvResolvers: typing.TypeAlias = tuple[tuple[str, typing.Callable[[Container], typing.Any]], ...]
    _CtxBindings: typing.TypeAlias = tuple[tuple[str, ContextProvider[typing.Any], SignatureItem], ...]

_SCOPE_ERRORS = (exceptions.ScopeNotInitializedError, exceptions.ScopeSkippedError)
_STEP_ERRORS = (exceptions.ResolutionError, *_SCOPE_ERRORS)


def compile_resolver(
    provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry"
) -> "typing.Callable[[Container], typing.Any]":
    """Return `provider`'s compiled resolver. All provider types compile; no interpreted fallback ships."""
    if type(provider) is Factory:
        if provider.cache_settings is None:
            return _compile_transient_factory(provider, registry)
        return _compile_cached_factory(provider, registry)
    # BRIDGE (temporary, Task 4 replaces this): route uncompiled types through the interpreted path.
    return lambda c: c._resolve_provider_interpreted(provider)  # noqa: SLF001


def _compile_transient_factory(  # noqa: C901 (inlined hot path: kept flat to hold the per-node frame at 1)
    f: "Factory[typing.Any]", registry: "ProvidersRegistry"
) -> "typing.Callable[[Container], typing.Any]":
    plan = registry.plan_for(f, f._parsed_kwargs, f._kwargs)  # noqa: SLF001
    if plan.unwireable:
        # Broken graph: bridge so the interpreted path raises the exact ArgumentResolutionError.
        return lambda c: c._resolve_provider_interpreted(f)  # noqa: SLF001
    prov: _ProvResolvers = tuple((name, registry.resolver_for(p)) for name, p in plan.provider_kwargs.items())
    static = plan.static_kwargs
    ctx: _CtxBindings = tuple((name, cp, item) for name, (cp, item) in plan.context_kwargs.items())
    pure = plan.pure_provider
    scope = f.scope
    pid = f.provider_id
    resolution_step = f._resolution_step  # noqa: SLF001
    resolve_context = f._resolve_context_value  # noqa: SLF001
    creator = f._creator  # noqa: SLF001

    def resolve(container: "Container") -> typing.Any:  # noqa: ANN401
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        # Navigate once; same-scope deps (the common case) skip the find_container call.
        target = container if container.scope == scope else _navigate(container, scope, resolution_step)
        if target.closed:
            target._warn_and_reopen_if_closed()  # noqa: SLF001
        try:  # inlined Factory._resolve_kwargs
            kwargs = {name: r(target) for name, r in prov}
            if not pure:
                kwargs.update(static)
                for name, cp, item in ctx:
                    value = resolve_context(target, name, cp, item)
                    if value is not types.UNSET:
                        kwargs[name] = value
        except _STEP_ERRORS as exc:
            exc.prepend_step(resolution_step())
            raise
        try:  # inlined Factory._call_creator
            return creator(**kwargs)
        except TypeError as exc:
            if exc.__traceback__ is not None and exc.__traceback__.tb_next is not None:
                raise  # a TypeError from inside the creator body propagates unchanged
            error = exceptions.CreatorCallError(creator=creator, original_error=exc)
            error.prepend_step(resolution_step())
            raise error from exc

    return resolve


def _compile_cached_factory(  # noqa: C901 (two closures: build_kwargs cold-miss path, resolve warm-hit path)
    f: "Factory[typing.Any]", registry: "ProvidersRegistry"
) -> "typing.Callable[[Container], typing.Any]":
    plan = registry.plan_for(f, f._parsed_kwargs, f._kwargs)  # noqa: SLF001
    if plan.unwireable:
        return lambda c: c._resolve_provider_interpreted(f)  # noqa: SLF001
    prov: _ProvResolvers = tuple((name, registry.resolver_for(p)) for name, p in plan.provider_kwargs.items())
    static = plan.static_kwargs
    ctx: _CtxBindings = tuple((name, cp, item) for name, (cp, item) in plan.context_kwargs.items())
    pure = plan.pure_provider
    scope = f.scope
    pid = f.provider_id
    resolution_step = f._resolution_step  # noqa: SLF001
    resolve_context = f._resolve_context_value  # noqa: SLF001
    call_creator = f._call_creator  # noqa: SLF001  # cold-miss only; reused (not hot)

    def build_kwargs(target: "Container") -> dict[str, typing.Any]:
        try:
            kwargs = {name: r(target) for name, r in prov}
            if not pure:
                kwargs.update(static)
                for name, cp, item in ctx:
                    value = resolve_context(target, name, cp, item)
                    if value is not types.UNSET:
                        kwargs[name] = value
        except _STEP_ERRORS as exc:
            exc.prepend_step(resolution_step())
            raise
        return kwargs

    def resolve(container: "Container") -> typing.Any:  # noqa: ANN401
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        target = container if container.scope == scope else _navigate(container, scope, resolution_step)
        if target.closed:
            target._warn_and_reopen_if_closed()  # noqa: SLF001
        cache_item = target.cache_registry.fetch_cache_item(f)
        cached = cache_item.cache
        if cached is not types.UNSET:
            return cached  # warm hit: skip the get_or_create frame (same sentinel check it makes)
        value, created = cache_item.get_or_create(
            target._lock,  # noqa: SLF001
            resolve=lambda: build_kwargs(target),
            create=call_creator,
        )
        if created:
            target.cache_registry.mark_created(cache_item)
        return value

    return resolve


def _navigate(
    container: "Container",
    scope: typing.Any,  # noqa: ANN401
    resolution_step: "typing.Callable[[], exceptions.ResolutionStep]",
) -> "Container":
    """Cross-scope target lookup; prepends the resolution step to a scope error, as the interpreted path does."""
    try:
        return container.find_container(scope)
    except _SCOPE_ERRORS as exc:
        exc.prepend_step(resolution_step())
        raise
