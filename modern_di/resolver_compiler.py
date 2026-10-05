"""Compile one resolver per provider: the single resolve path.

A ``Factory`` resolver is generated from a source template, specialised to the factory's shape
(arity, argument names, static kwargs, caching), and ``exec``'d with the factory's constants as its
globals. An ``Alias`` compiles to its source's resolver, so a parent's error clause redraws the
redirect hops it skipped. Every other provider type compiles to a small closure. An overridden
provider compiles to its override value, so the resolvers never consult the overrides registry;
applying an override drops the compiled resolvers instead (see
``ProvidersRegistry.drop_resolvers``). Why a template and not shared helpers: see
docs/adr/0001-resolver-hot-path-generated-source.md.

The template reaches into `Container._lock`/`_scope_map` and `CacheRegistry._items` to stay
within that frame budget. No linter sees the template, so those reaches are outside every suppression here.
"""

import enum
import functools
import itertools
import linecache
import typing

from modern_di import exceptions, types
from modern_di.dependency_graph import redirect_hops
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.alias import Alias
from modern_di.providers.container_provider import container_provider
from modern_di.providers.context_provider import ContextProvider
from modern_di.providers.factory import Factory


if typing.TYPE_CHECKING:
    from types import CodeType

    from modern_di import Container
    from modern_di.registries.providers_registry import ProvidersRegistry
    from modern_di.wiring import WiringPlan

    Resolver: typing.TypeAlias = typing.Callable[[Container], typing.Any]

_SCOPE_ERRORS = (exceptions.ScopeNotInitializedError, exceptions.ScopeSkippedError)
STEP_ERRORS = (exceptions.ResolutionError,)


def compile_resolver(provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry") -> "Resolver":
    """Return `provider`'s compiled resolver; an overridden provider resolves to its override value."""
    override = registry.overrides.fetch_override(provider.provider_id)
    if override is not types.UNSET:
        return _compile_constant(override)
    if type(provider) is Factory:
        return _compile_factory(provider, registry)
    if type(provider) is Alias:
        return _compile_alias(provider, registry)
    if provider is container_provider:
        return _resolve_to_container
    if type(provider) is ContextProvider:
        return _compile_context_provider(provider)
    msg = f"no compiled resolver for provider type {type(provider).__name__}"
    raise TypeError(msg)


_NAVIGATE = """\
    if container.scope == scope:
        target = container
    else:
        target = container._scope_map.get(scope)
        if target is None:
            target = _navigate(container, scope, resolution_step)
    if target._closed:
        raise ContainerClosedError(container_scope=target.scope)
"""

_BUILD_ARGUMENTS = """\
    try:
{build}
    except ContextValueNotSetError as exc:
        name = [*edges][arg_lines[exc.__traceback__.tb_lineno]]
        if not exc.dependency_path:
            exc.name_parameter(name)
        exc.prepend_step(resolution_step(), *redirect_hops(edges[name], target))
        raise
    except _STEP_ERRORS as exc:
        name = [*edges][arg_lines[exc.__traceback__.tb_lineno]]
        exc.prepend_step(resolution_step(), *redirect_hops(edges[name], target))
        raise
"""

_CALL_CREATOR = """\
    try:
        return creator({args})
    except TypeError as exc:
        error = CreatorCallError.from_type_error(creator=creator, exc=exc, resolution_step=resolution_step)
        if error is None:
            raise
        raise error from exc
    except _STEP_ERRORS as exc:
        exc.prepend_step(resolution_step())
        raise
"""

_TRANSIENT = "def resolve(container):\n" + _NAVIGATE + _BUILD_ARGUMENTS + _CALL_CREATOR

_CACHED = (
    "def build(target):\n"
    + _BUILD_ARGUMENTS
    + "    return {built}\n\ndef create(built):\n"
    + _CALL_CREATOR
    + "\ndef resolve(container):\n"
    + _NAVIGATE
    + """\
    cache_registry = target._cache_registry
    cache_item = cache_registry._items.get(pid)
    if cache_item is None:
        cache_item = cache_registry.fetch_cache_item(provider)
    cached = cache_item.cache
    if cached is not UNSET:
        return cached
    value, created = cache_item.get_or_create(target._lock, resolve=partial(build, target), create=create)
    if created:
        cache_registry.mark_created(cache_item)
    return value
"""
)


def _source(arity: int, names: tuple[str, ...] | None, static: bool, cached: bool) -> tuple[str, dict[int, int]]:
    """Generate the resolver source for one shape, and map each resolver call's line to its argument index."""
    if names is None:
        build = [f"        a{i} = r{i}(target)" for i in range(arity)] or ["        pass"]
        first_call = 0
        args = ", ".join(f"a{i}" for i in range(arity))
        built = "(" + "".join(f"a{i}, " for i in range(arity)) + ")"
        star = "*"
    else:
        calls = [f"            {name!r}: r{i}(target)," for i, name in enumerate(names)]
        build = ["        kwargs = {", *calls, "        }"]
        first_call = 1
        if static:
            build.append("        kwargs.update(static)")
        args, built, star = "**kwargs", "kwargs", "**"
    if cached:
        template, args = _CACHED, f"{star}built"
    else:
        template = _TRANSIENT
    build_line = template[: template.index("{build}")].count("\n") + 1
    arg_lines = {build_line + first_call + i: i for i in range(arity)}
    return template.format(build="\n".join(build), built=built, args=args), arg_lines


_shape_ids = itertools.count()


@functools.cache
def _code(arity: int, names: tuple[str, ...] | None, static: bool, cached: bool) -> "tuple[CodeType, dict[int, int]]":
    """Compile one shape's source, so factories of one shape share a code object."""
    source, arg_lines = _source(arity, names, static, cached)
    filename = f"<modern_di resolver shape {next(_shape_ids)}>"
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    return compile(source, filename, "exec"), arg_lines


def _compile_factory(f: "Factory[typing.Any]", registry: "ProvidersRegistry") -> "Resolver":
    plan = f._wiring_plan(registry)
    if plan.unwireable:
        return _compile_unwireable_factory(f, plan)
    positional = f._can_call_positionally(plan)
    code, arg_lines = _code(
        len(plan.provider_kwargs),
        None if positional else tuple(plan.provider_kwargs),
        bool(plan.static_kwargs),
        f.cache_settings is not None,
    )
    namespace: dict[str, typing.Any] = {
        "provider": f,
        "pid": f.provider_id,
        "scope": f.scope,
        "creator": f._creator,
        "resolution_step": f._resolution_step,
        "edges": plan.provider_kwargs,
        "arg_lines": arg_lines,
        "static": plan.static_kwargs,
        "UNSET": types.UNSET,
        "partial": functools.partial,
        "_navigate": _navigate,
        "_STEP_ERRORS": STEP_ERRORS,
        "CreatorCallError": exceptions.CreatorCallError,
        "ContainerClosedError": exceptions.ContainerClosedError,
        "ContextValueNotSetError": exceptions.ContextValueNotSetError,
        "redirect_hops": redirect_hops,
        **{f"r{i}": registry.resolver_for(p) for i, p in enumerate(plan.provider_kwargs.values())},
    }
    exec(code, namespace)  # noqa: S102  # the source is a fixed template; user data enters only via `namespace`
    resolve = namespace["resolve"]
    resolve.__qualname__ = f"resolve[{f.display_name}]"
    return resolve


def _compile_constant(value: typing.Any) -> "Resolver":
    def resolve(_: "Container") -> typing.Any:
        return value

    return resolve


def _compile_unwireable_factory(f: "Factory[typing.Any]", plan: "WiringPlan") -> "Resolver":
    """Compile a resolver that always raises for the factory's first unwireable parameter, freshly built per call."""
    scope = f.scope
    resolution_step = f._resolution_step
    build_error = f._argument_resolution_error
    arg_name, item = plan.unwireable[0]

    def resolve(container: "Container") -> typing.Any:
        target = container if container.scope == scope else _navigate(container, scope, resolution_step)
        if target._closed:
            raise exceptions.ContainerClosedError(container_scope=target.scope)
        error = build_error(arg_name=arg_name, item=item, registry=target._providers_registry)
        error.prepend_step(resolution_step())
        raise error

    return resolve


def _compile_alias(a: "Alias[typing.Any]", registry: "ProvidersRegistry") -> "Resolver":
    """Compile to the source's own resolver; a missing source compiles to a resolver that raises."""
    source_type = a._source_type
    source = registry.find_provider(source_type)
    if source is not None:
        return registry.resolver_for(source)

    def resolve(_: "Container") -> typing.Any:
        error = exceptions.AliasSourceNotRegisteredError(source_type=source_type)
        error.prepend_step(a._resolution_step())
        raise error

    return resolve


def _resolve_to_container(container: "Container") -> typing.Any:
    return container


def _compile_context_provider(cp: "ContextProvider[typing.Any]") -> "Resolver":
    scope = cp.scope
    context_type = cp.context_type
    default = cp.default
    resolution_step = cp._resolution_step

    def resolve(container: "Container") -> typing.Any:
        if container.scope == scope:
            target = container
        else:
            target = container._scope_map.get(scope)
            if target is None:
                target = _navigate(container, scope, resolution_step)
        if target._closed:
            raise exceptions.ContainerClosedError(container_scope=target.scope)
        context = target._context_registry.context
        # Not `.get(key, UNSET)`: that skips a dict subclass's `__contains__`/`__getitem__`.
        if context_type in context:
            return context[context_type]
        if default is not types.UNSET:
            return default
        raise exceptions.ContextValueNotSetError(context_type=context_type, provider_scope=scope)

    return resolve


def _navigate(
    container: "Container",
    scope: enum.IntEnum,
    resolution_step: "typing.Callable[[], exceptions.ResolutionStep]",
) -> "Container":
    """Miss path for a scope absent from `_scope_map`; the scope error carries this provider's resolution step."""
    try:
        return container.find_container(scope)
    except _SCOPE_ERRORS as exc:
        exc.prepend_step(resolution_step())
        raise
