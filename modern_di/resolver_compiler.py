"""Compile one flat closure resolver per provider (the single resolve path).

Each resolver front-guards its own override, navigates its target once (same-scope deps skip
the navigation via an int compare), inlines the kwargs build and creator call, and calls its
dependencies' resolvers by reference. Behavior-sensitive helpers (`_resolution_step`,
`prepend_step`) are reused, not reimplemented. Context kwargs are folded at compile time --
`ContextProvider.scope` and `.context_type` are fixed once registered, see
architecture/providers.md -- so the whole context lookup is inline here and owns its behaviour.
"""

import functools
import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.alias import Alias
from modern_di.providers.container_provider import container_provider
from modern_di.providers.context_provider import ContextProvider
from modern_di.providers.factory import Factory
from modern_di.wiring import _Absent, absent_disposition


if typing.TYPE_CHECKING:
    from modern_di import Container
    from modern_di.registries.providers_registry import ProvidersRegistry
    from modern_di.types_parser import SignatureItem
    from modern_di.wiring import WiringPlan

    _ProvResolvers: typing.TypeAlias = tuple[tuple[str, typing.Callable[[Container], typing.Any]], ...]
    #: name, ContextProvider.provider_id, its scope, its context_type, absent disposition, item.
    #: Folded at compile time; the identity of a registered ContextProvider does not change.
    _CtxBindings: typing.TypeAlias = tuple[tuple[str, int, typing.Any, type, _Absent, SignatureItem], ...]

_SCOPE_ERRORS = (exceptions.ScopeNotInitializedError, exceptions.ScopeSkippedError)
_STEP_ERRORS = (exceptions.ResolutionError, *_SCOPE_ERRORS)


def _can_call_positionally(f: "Factory[typing.Any]", plan: "WiringPlan") -> bool:
    """Whether `f`'s creator can be called positionally instead of with `**kwargs`.

    Eligible only when every parsed parameter is a positional-or-keyword provider dependency, in
    signature order, with nothing omitted (no static, no context, no default-omitted, no
    keyword-only, no kwargs-overlay extra). Exactly this graph gets the positional call; anything
    else keeps `creator(**kwargs)`. When in doubt, exclude.
    """
    if not plan.pure_provider:  # pure_provider already means no static and no context kwargs
        return False
    names = tuple(f._parsed_kwargs)
    if tuple(plan.provider_kwargs) != names:
        return False  # a param was omitted/reordered, or a kwargs-overlay added an extra -> not a clean prefix
    if any(item.is_keyword_only for item in f._parsed_kwargs.values()):
        return False
    # A positional-only param is dropped from _parsed_kwargs by the parser, so the remaining names
    # can look like a clean prefix while a positional call would bind them to the wrong slots.
    return not (names and f._has_positional_only_gap)


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
    plan = registry.plan_for(f, f._parsed_kwargs, f._kwargs)
    if plan.unwireable:
        return _compile_unwireable_factory(f, plan)
    prov: _ProvResolvers = tuple((name, registry.resolver_for(p)) for name, p in plan.provider_kwargs.items())
    static = plan.static_kwargs
    ctx: _CtxBindings = tuple(
        (name, cp.provider_id, cp.scope, cp.context_type, absent_disposition(item), item)
        for name, (cp, item) in plan.context_kwargs.items()
    )
    pure = plan.pure_provider
    scope = f.scope
    pid = f.provider_id
    resolution_step = f._resolution_step
    build_arg_error = f._argument_resolution_error
    creator = f._creator

    if _can_call_positionally(f, plan):
        # Positional fast path; `pure` is True here, so no static/context folding runs.
        # See architecture/performance.md.
        pos = tuple(r for _name, r in prov)

        # Arity ladder. `len(pos)` is fixed at compile time, so 0 and 1 deps get a closure that
        # names its argument and calls the creator directly -- no list build, no
        # CALL_FUNCTION_EX unpack, and below 3.12 no comprehension frame either. Each rung is a
        # full copy for the same reason the rest of this module is: a shared helper would cost a
        # frame per node -- which is also why the ladder stops at 1. Every measured win lives at
        # arity 0 and 1 (leaves and chains); rungs beyond that duplicate the closure's whole
        # branch set for a gain no scenario in `benchmarks/` shows. Arity 2+ falls through to the
        # generic star-call below.
        if len(pos) == 0:

            def resolve_arity0(container: "Container") -> typing.Any:
                overrides = container.overrides_registry
                if overrides.has_overrides:
                    override = overrides.fetch_override(pid)
                    if override is not types.UNSET:
                        return override
                target = container if container.scope == scope else _navigate(container, scope, resolution_step)
                if target.closed:
                    target._prepare()
                try:
                    return creator()
                except TypeError as exc:
                    error = exceptions.CreatorCallError.from_type_error(
                        creator=creator, exc=exc, resolution_step=resolution_step
                    )
                    if error is None:
                        raise
                    raise error from exc

            return resolve_arity0

        if len(pos) == 1:
            (r0,) = pos

            def resolve_arity1(container: "Container") -> typing.Any:
                overrides = container.overrides_registry
                if overrides.has_overrides:
                    override = overrides.fetch_override(pid)
                    if override is not types.UNSET:
                        return override
                target = container if container.scope == scope else _navigate(container, scope, resolution_step)
                if target.closed:
                    target._prepare()
                try:
                    a0 = r0(target)
                except _STEP_ERRORS as exc:
                    exc.prepend_step(resolution_step())
                    raise
                try:
                    return creator(a0)
                except TypeError as exc:
                    error = exceptions.CreatorCallError.from_type_error(
                        creator=creator, exc=exc, resolution_step=resolution_step
                    )
                    if error is None:
                        raise
                    raise error from exc

            return resolve_arity1

        def resolve_positional(container: "Container") -> typing.Any:
            # Inlined per closure, not extracted: frame budget — see architecture/performance.md.
            overrides = container.overrides_registry
            if overrides.has_overrides:
                override = overrides.fetch_override(pid)
                if override is not types.UNSET:
                    return override
            target = container if container.scope == scope else _navigate(container, scope, resolution_step)
            if target.closed:
                target._prepare()
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
                    raise
                raise error from exc

        return resolve_positional

    # The folded context lookup is inline by design: extracting it would cost a Python frame
    # per context kwarg, which is the budget this module exists to hold.
    def resolve(container: "Container") -> typing.Any:  # noqa: C901, PLR0912
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        target = container if container.scope == scope else _navigate(container, scope, resolution_step)
        if target.closed:
            target._prepare()
        try:  # build the kwargs dict from provider/static/context bindings
            kwargs = {name: r(target) for name, r in prov}
            if not pure:
                kwargs.update(static)
                # `find_container`, never `_navigate`: that helper prepends a resolution step and
                # the `except` below prepends this factory's own, rendering the caller twice.
                for name, cpid, cscope, ctype, disp, item in ctx:
                    if overrides.has_overrides:
                        override = overrides.fetch_override(cpid)
                        if override is not types.UNSET:
                            kwargs[name] = override
                            continue
                    holder = target if target.scope == cscope else target.find_container(cscope)
                    if holder.closed:
                        holder._prepare()
                    value = holder.context_registry.find_context(ctype)
                    if value is not types.UNSET:
                        kwargs[name] = value
                    elif disp is _Absent.NULL:
                        kwargs[name] = None
                    elif disp is not _Absent.OMIT:
                        raise build_arg_error(arg_name=name, item=item)
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
                raise
            raise error from exc

    return resolve


def _compile_cached_factory(  # noqa: C901, PLR0915 (cold-miss builder pair: positional + kwargs, plus the warm-hit resolve closure)
    f: "Factory[typing.Any]", registry: "ProvidersRegistry"
) -> "typing.Callable[[Container], typing.Any]":
    plan = registry.plan_for(f, f._parsed_kwargs, f._kwargs)
    if plan.unwireable:
        return _compile_unwireable_factory(f, plan)
    prov: _ProvResolvers = tuple((name, registry.resolver_for(p)) for name, p in plan.provider_kwargs.items())
    static = plan.static_kwargs
    ctx: _CtxBindings = tuple(
        (name, cp.provider_id, cp.scope, cp.context_type, absent_disposition(item), item)
        for name, (cp, item) in plan.context_kwargs.items()
    )
    pure = plan.pure_provider
    scope = f.scope
    pid = f.provider_id
    resolution_step = f._resolution_step
    build_arg_error = f._argument_resolution_error
    creator = f._creator  # cold-miss only (not hot)
    call_creator = f._call_creator  # cold-miss only; reused (not hot)

    # Cold-miss builder + creator call, positional or kwargs. Both share the two-phase error handling.
    if _can_call_positionally(f, plan):
        pos = tuple(r for _name, r in prov)

        def build_args(target: "Container") -> list[typing.Any]:
            try:
                return [r(target) for r in pos]
            except _STEP_ERRORS as exc:
                exc.prepend_step(resolution_step())
                raise

        def create_positional(args: list[typing.Any]) -> typing.Any:
            try:
                return creator(*args)
            except TypeError as exc:
                error = exceptions.CreatorCallError.from_type_error(
                    creator=creator, exc=exc, resolution_step=resolution_step
                )
                if error is None:
                    raise
                raise error from exc

        build_cold = build_args
        create_cold = create_positional
    else:

        def build_kwargs(target: "Container") -> dict[str, typing.Any]:
            try:
                kwargs = {name: r(target) for name, r in prov}
                if not pure:
                    kwargs.update(static)
                    overrides = target.overrides_registry
                    # `find_container`, never `_navigate` -- see the transient copy above.
                    for name, cpid, cscope, ctype, disp, item in ctx:
                        if overrides.has_overrides:
                            override = overrides.fetch_override(cpid)
                            if override is not types.UNSET:
                                kwargs[name] = override
                                continue
                        holder = target if target.scope == cscope else target.find_container(cscope)
                        if holder.closed:
                            holder._prepare()
                        value = holder.context_registry.find_context(ctype)
                        if value is not types.UNSET:
                            kwargs[name] = value
                        elif disp is _Absent.NULL:
                            kwargs[name] = None
                        elif disp is not _Absent.OMIT:
                            raise build_arg_error(arg_name=name, item=item)
            except _STEP_ERRORS as exc:
                exc.prepend_step(resolution_step())
                raise
            return kwargs

        build_cold = build_kwargs
        create_cold = call_creator

    def resolve(container: "Container") -> typing.Any:
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        target = container if container.scope == scope else _navigate(container, scope, resolution_step)
        if target.closed:
            target._prepare()
        # Inlined memo hit; the method is called only on a miss, where its `setdefault` makes
        # concurrent first-resolvers share one CacheItem. See architecture/performance.md.
        cache_registry = target.cache_registry
        cache_item = cache_registry._items.get(pid)
        if cache_item is None:
            cache_item = cache_registry.fetch_cache_item(f)
        cached = cache_item.cache
        if cached is not types.UNSET:
            return cached
        value, created = cache_item.get_or_create(
            target._lock,
            # `partial`, never a lambda closing over `target`: a closure promotes `target` to a cell,
            # so MAKE_CELL runs in this resolver's prologue on every warm hit too. See
            # architecture/performance.md.
            resolve=functools.partial(build_cold, target),
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
    resolution_step = f._resolution_step
    build_error = f._argument_resolution_error
    arg_name, item = plan.unwireable[0]

    def resolve(container: "Container") -> typing.Any:
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        target = container if container.scope == scope else _navigate(container, scope, resolution_step)
        if target.closed:
            target._prepare()
        error = build_error(arg_name=arg_name, item=item, registry=target.providers_registry)
        error.prepend_step(resolution_step())
        raise error

    return resolve


def _compile_alias(a: "Alias[typing.Any]") -> "typing.Callable[[Container], typing.Any]":
    """Call the source's compiled resolver directly, wrapping scope/resolution errors with its own step.

    The source lookup and its resolver memo read are inlined, and nothing is cached: a source
    registered later is picked up on the next resolve. A single try/except covers the
    dangling-source lookup and the forwarded resolve, so both carry this alias's resolution step.
    """
    pid = a.provider_id
    source_type = a._source_type
    resolution_step = a._resolution_step
    find_source = a._find_source

    def resolve(container: "Container") -> typing.Any:
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        try:
            registry = container.providers_registry
            source = registry._providers.get(source_type)
            if source is None:
                source = find_source(container)  # raises AliasSourceNotRegisteredError
            source_resolver = registry._resolvers.get(source.provider_id)
            if source_resolver is None:
                source_resolver = registry.resolver_for(source)
            return source_resolver(container)
        except _STEP_ERRORS as exc:
            exc.prepend_step(resolution_step())
            raise

    return resolve


def _compile_container_provider() -> "typing.Callable[[Container], typing.Any]":
    """Resolve to the resolving container itself — no scope navigation."""
    pid = container_provider.provider_id

    def resolve(container: "Container") -> typing.Any:
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

    def resolve(container: "Container") -> typing.Any:
        overrides = container.overrides_registry
        if overrides.has_overrides:
            override = overrides.fetch_override(pid)
            if override is not types.UNSET:
                return override
        return resolve_bound(container)

    return resolve


def _navigate(
    container: "Container",
    scope: typing.Any,
    resolution_step: "typing.Callable[[], exceptions.ResolutionStep]",
) -> "Container":
    """Cross-scope target lookup; prepends the resolution step to a scope error, as the interpreted path does."""
    try:
        return container.find_container(scope)
    except _SCOPE_ERRORS as exc:
        exc.prepend_step(resolution_step())
        raise
