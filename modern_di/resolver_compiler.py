"""Compile one flat closure resolver per provider (the single resolve path).

Each resolver front-guards its own override, navigates its target once (same-scope deps skip
the navigation via an int compare), inlines the kwargs build and creator call, and calls its
dependencies' resolvers by reference. Behavior-sensitive helpers (`_resolution_step`,
`_resolve_context_value`, `prepend_step`) are reused, not reimplemented.
"""

import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.alias import Alias
from modern_di.providers.container_provider import container_provider
from modern_di.providers.context_provider import ContextProvider
from modern_di.providers.factory import Factory


if typing.TYPE_CHECKING:
    from modern_di import Container
    from modern_di.registries.providers_registry import ProvidersRegistry
    from modern_di.types_parser import SignatureItem
    from modern_di.wiring import WiringPlan

    _ProvResolvers: typing.TypeAlias = tuple[tuple[str, typing.Callable[[Container], typing.Any]], ...]
    _CtxBindings: typing.TypeAlias = tuple[tuple[str, ContextProvider[typing.Any], SignatureItem], ...]

_SCOPE_ERRORS = (exceptions.ScopeNotInitializedError, exceptions.ScopeSkippedError)
_STEP_ERRORS = (exceptions.ResolutionError, *_SCOPE_ERRORS)


def _positional_names(f: "Factory[typing.Any]", plan: "WiringPlan") -> "tuple[str, ...] | None":
    """Return the ordered param names to pass positionally, or None if the creator must use kwargs.

    Eligible only when every parsed parameter is a positional-or-keyword provider dependency, in
    signature order, with nothing omitted (no static, no context, no default-omitted, no
    keyword-only, no kwargs-overlay extra). Exactly this graph gets the positional call; anything
    else keeps `creator(**kwargs)`. When in doubt, exclude.
    """
    if not plan.pure_provider:  # pure_provider already means no static and no context kwargs
        return None
    names = tuple(f._parsed_kwargs)  # noqa: SLF001
    if tuple(plan.provider_kwargs) != names:
        return None  # a param was omitted/reordered, or a kwargs-overlay added an extra -> not a clean prefix
    if any(item.is_keyword_only for item in f._parsed_kwargs.values()):  # noqa: SLF001
        return None
    if names and f._has_positional_only_gap:  # noqa: SLF001
        return None  # positional-only param, dropped from _parsed_kwargs by the parser, would shift positional binding
    return names


def compile_resolver(
    provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry"
) -> "typing.Callable[[Container], typing.Any]":
    """Return `provider`'s compiled resolver. All provider types compile; no interpreted fallback ships."""
    if type(provider) is Factory:
        if provider.cache_settings is None:
            return _compile_transient_factory(provider, registry)
        return _compile_cached_factory(provider, registry)
    if type(provider) is Alias:
        return _compile_alias(provider)
    if provider is container_provider:
        return _compile_container_provider()
    if type(provider) is ContextProvider:
        return _compile_context_provider(provider)
    msg = f"no compiled resolver for provider type {type(provider).__name__}"
    raise TypeError(msg)  # every provider type is compiled; a new type must add a branch here


def _compile_transient_factory(  # noqa: C901, PLR0915 (two hot-path closures: positional + kwargs, each flat to hold the per-node frame at 1)
    f: "Factory[typing.Any]", registry: "ProvidersRegistry"
) -> "typing.Callable[[Container], typing.Any]":
    plan = registry.plan_for(f, f._parsed_kwargs, f._kwargs)  # noqa: SLF001
    if plan.unwireable:
        return _compile_unwireable_factory(f, plan)
    prov: _ProvResolvers = tuple((name, registry.resolver_for(p)) for name, p in plan.provider_kwargs.items())
    static = plan.static_kwargs
    ctx: _CtxBindings = tuple((name, cp, item) for name, (cp, item) in plan.context_kwargs.items())
    pure = plan.pure_provider
    scope = f.scope
    pid = f.provider_id
    resolution_step = f._resolution_step  # noqa: SLF001
    resolve_context = f._resolve_context_value  # noqa: SLF001
    creator = f._creator  # noqa: SLF001

    if _positional_names(f, plan) is not None:
        # Fast path: the whole signature is provider deps, in order — call positionally, skipping
        # the measured 4-6x **kwargs cost. `pure` is True here, so no static/context folding runs.
        pos = tuple(r for _name, r in prov)

        def resolve_positional(container: "Container") -> typing.Any:  # noqa: ANN401
            # Override front-guard is inlined into every closure (not extracted): the compiled dispatch
            # checks no overrides centrally, and a helper would add one Python frame per node.
            overrides = container.overrides_registry
            if overrides.has_overrides:
                override = overrides.fetch_override(pid)
                if override is not types.UNSET:
                    return override
            target = container if container.scope == scope else _navigate(container, scope, resolution_step)
            if target.closed:
                target._raise_if_closed()  # noqa: SLF001
            try:  # build the positional args from the dependency resolvers (a dependency can raise ResolutionError)
                args = [r(target) for r in pos]
            except _STEP_ERRORS as exc:
                exc.prepend_step(resolution_step())
                raise
            try:  # inlined Factory._call_creator, positional
                return creator(*args)
            except TypeError as exc:
                error = exceptions.CreatorCallError.from_type_error(
                    creator=creator, exc=exc, resolution_step=resolution_step
                )
                if error is None:
                    raise  # a TypeError from inside the creator body propagates unchanged
                raise error from exc

        return resolve_positional

    def resolve(container: "Container") -> typing.Any:  # noqa: ANN401
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        # Navigate once; same-scope deps (the common case) skip the find_container call.
        target = container if container.scope == scope else _navigate(container, scope, resolution_step)
        if target.closed:
            target._raise_if_closed()  # noqa: SLF001
        try:  # build the kwargs dict from provider/static/context bindings
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
            error = exceptions.CreatorCallError.from_type_error(
                creator=creator, exc=exc, resolution_step=resolution_step
            )
            if error is None:
                raise  # a TypeError from inside the creator body propagates unchanged
            raise error from exc

    return resolve


def _compile_cached_factory(  # noqa: C901, PLR0915 (cold-miss builder pair: positional + kwargs, plus the warm-hit resolve closure)
    f: "Factory[typing.Any]", registry: "ProvidersRegistry"
) -> "typing.Callable[[Container], typing.Any]":
    plan = registry.plan_for(f, f._parsed_kwargs, f._kwargs)  # noqa: SLF001
    if plan.unwireable:
        return _compile_unwireable_factory(f, plan)
    prov: _ProvResolvers = tuple((name, registry.resolver_for(p)) for name, p in plan.provider_kwargs.items())
    static = plan.static_kwargs
    ctx: _CtxBindings = tuple((name, cp, item) for name, (cp, item) in plan.context_kwargs.items())
    pure = plan.pure_provider
    scope = f.scope
    pid = f.provider_id
    resolution_step = f._resolution_step  # noqa: SLF001
    resolve_context = f._resolve_context_value  # noqa: SLF001
    creator = f._creator  # noqa: SLF001  # cold-miss only (not hot)
    call_creator = f._call_creator  # noqa: SLF001  # cold-miss only; reused (not hot)

    # cold-miss builder + creator call: positional when the whole signature is provider deps in
    # order (skips the **kwargs cost), else the kwargs pair. Both share the two-phase error handling.
    if _positional_names(f, plan) is not None:
        pos = tuple(r for _name, r in prov)

        def build_args(target: "Container") -> list[typing.Any]:
            try:
                return [r(target) for r in pos]
            except _STEP_ERRORS as exc:
                exc.prepend_step(resolution_step())
                raise

        def create_positional(args: list[typing.Any]) -> typing.Any:  # noqa: ANN401
            try:
                return creator(*args)
            except TypeError as exc:
                error = exceptions.CreatorCallError.from_type_error(
                    creator=creator, exc=exc, resolution_step=resolution_step
                )
                if error is None:
                    raise  # a TypeError from inside the creator body propagates unchanged
                raise error from exc

        build_cold = build_args
        create_cold = create_positional
    else:

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

        build_cold = build_kwargs
        create_cold = call_creator

    def resolve(container: "Container") -> typing.Any:  # noqa: ANN401
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        target = container if container.scope == scope else _navigate(container, scope, resolution_step)
        if target.closed:
            target._raise_if_closed()  # noqa: SLF001
        cache_item = target.cache_registry.fetch_cache_item(f)
        cached = cache_item.cache
        if cached is not types.UNSET:
            return cached  # warm hit: skip the get_or_create frame (same sentinel check it makes)
        value, created = cache_item.get_or_create(
            target._lock,  # noqa: SLF001
            resolve=lambda: build_cold(target),
            # positional/kwargs builders have distinct arg types; get_or_create feeds each its own.
            create=typing.cast("typing.Callable[[typing.Any], typing.Any]", create_cold),
        )
        if created:
            target.cache_registry.mark_created(cache_item)
        return value

    return resolve


def _compile_unwireable_factory(
    f: "Factory[typing.Any]", plan: "WiringPlan"
) -> "typing.Callable[[Container], typing.Any]":
    """Compile the always-raising resolver for a Factory with an unwireable parameter.

    Front-guard the override (an unwireable factory can still be overridden with a mock), navigate
    to the scope-correct target (a scope error there wins, with its step prepended), then raise the
    freshly built error with this factory's own resolution step. The error is built on every call
    (never memoized) so `prepend_step`'s mutation cannot leak a breadcrumb across repeated resolves.
    """
    pid = f.provider_id
    scope = f.scope
    resolution_step = f._resolution_step  # noqa: SLF001
    build_error = f._argument_resolution_error  # noqa: SLF001
    arg_name, item = plan.unwireable[0]

    def resolve(container: "Container") -> typing.Any:  # noqa: ANN401
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        target = container if container.scope == scope else _navigate(container, scope, resolution_step)
        if target.closed:
            target._raise_if_closed()  # noqa: SLF001
        error = build_error(arg_name=arg_name, item=item, registry=target.providers_registry)
        error.prepend_step(resolution_step())
        raise error

    return resolve


def _compile_alias(a: "Alias[typing.Any]") -> "typing.Callable[[Container], typing.Any]":
    """Forward to the alias's source resolver, wrapping scope/resolution errors with its own step.

    A single try/except covers both the dangling-source lookup and the forwarded resolve, so a
    missing source and a source's own scope error each carry this alias's resolution step.
    """
    pid = a.provider_id
    resolution_step = a._resolution_step  # noqa: SLF001
    find_source = a._find_source  # noqa: SLF001

    def resolve(container: "Container") -> typing.Any:  # noqa: ANN401
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        try:
            return container.resolve_provider(find_source(container))
        except _STEP_ERRORS as exc:
            exc.prepend_step(resolution_step())
            raise

    return resolve


def _compile_container_provider() -> "typing.Callable[[Container], typing.Any]":
    """Resolve to the resolving container itself — no scope navigation."""
    pid = container_provider.provider_id

    def resolve(container: "Container") -> typing.Any:  # noqa: ANN401
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        return container

    return resolve


def _compile_context_provider(cp: "ContextProvider[typing.Any]") -> "typing.Callable[[Container], typing.Any]":
    """Front-guard the override, then delegate to the bound `ContextProvider.resolve`.

    Reuses the bound method so the unset-value `ContextValueNotSetError` stays identical, not
    reimplemented.
    """
    pid = cp.provider_id
    resolve_bound = cp.resolve

    def resolve(container: "Container") -> typing.Any:  # noqa: ANN401
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        return resolve_bound(container)

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
