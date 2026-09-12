"""Compile one resolver per provider: the single resolve path.

A ``Factory`` resolver is generated from a source template, specialised to the factory's
:class:`_Shape`, and ``exec``'d with the factory's constants as its globals. Every other provider
type compiles to a small closure. An overridden provider compiles to its override value, so the
resolvers never consult the overrides registry; applying an override drops the compiled
resolvers instead (see ``ProvidersRegistry.drop_resolvers``). Why a template and not shared
helpers: every all-Python single-copy design measured 25-80% slower (docs/introduction/performance.md).
"""

import dataclasses
import functools
import itertools
import linecache
import typing

from modern_di import exceptions, types
from modern_di.dependency_graph import redirect_step
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.alias import Alias
from modern_di.providers.container_provider import container_provider
from modern_di.providers.context_provider import ContextProvider
from modern_di.providers.factory import Factory
from modern_di.wiring import _Absent, absent_disposition


if typing.TYPE_CHECKING:
    from types import CodeType

    from modern_di import Container
    from modern_di.registries.providers_registry import ProvidersRegistry
    from modern_di.wiring import WiringPlan

    Resolver: typing.TypeAlias = typing.Callable[[Container], typing.Any]

_SCOPE_ERRORS = (exceptions.ScopeNotInitializedError, exceptions.ScopeSkippedError)
_STEP_ERRORS = (exceptions.ResolutionError, *_SCOPE_ERRORS)


def compile_resolver(provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry") -> "Resolver":
    """Return `provider`'s compiled resolver; an overridden provider resolves to its override value."""
    override = registry.overrides.fetch_override(provider.provider_id)
    if override is not types.UNSET:
        return _compile_constant(override)
    if type(provider) is Factory:
        return _compile_factory(provider, registry)
    if type(provider) is Alias:
        return _compile_alias(provider)
    if provider is container_provider:
        return _resolve_to_container
    if type(provider) is ContextProvider:
        return _compile_context_provider(provider)
    msg = f"no compiled resolver for provider type {type(provider).__name__}"
    raise TypeError(msg)


def _can_call_positionally(f: "Factory[typing.Any]", plan: "WiringPlan") -> bool:
    """Whether `f`'s creator can be called positionally.

    True when every parsed parameter is a positional-or-keyword provider dependency, in signature
    order, with nothing omitted, added, keyword-only or positional-only.
    """
    if not plan.pure_provider:
        return False
    names = tuple(f._parsed_kwargs)
    if tuple(plan.provider_kwargs) != names:
        return False
    if any(item.is_keyword_only for item in f._parsed_kwargs.values()):
        return False
    return not (names and f._has_positional_only_gap)


_TRANSIENT = """\
def resolve(container):
    target = container if container.scope == scope else _navigate(container, scope, resolution_step)
    if target.closed:
        target._prepare()
    try:
{build}
    except _STEP_ERRORS as exc:
        exc.prepend_step(resolution_step())
        raise
    try:
        return creator({args})
    except TypeError as exc:
        error = CreatorCallError.from_type_error(creator=creator, exc=exc, resolution_step=resolution_step)
        if error is None:
            raise
        raise error from exc
"""

_CACHED = """\
def build(target):
    try:
{build}
    except _STEP_ERRORS as exc:
        exc.prepend_step(resolution_step())
        raise
    return {built}

def create(built):
    try:
        return creator({star}built)
    except TypeError as exc:
        error = CreatorCallError.from_type_error(creator=creator, exc=exc, resolution_step=resolution_step)
        if error is None:
            raise
        raise error from exc

def resolve(container):
    target = container if container.scope == scope else _navigate(container, scope, resolution_step)
    if target.closed:
        target._prepare()
    cache_registry = target.cache_registry
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

_CONTEXT_FOLD = """\
        for name, context_scope, context_type, disposition, item in context:
            holder = target if target.scope == context_scope else target.find_container(context_scope)
            if holder.closed:
                holder._prepare()
            value = holder.context_registry.find_context(context_type)
            if value is not UNSET:
                kwargs[name] = value
            elif disposition is NULL:
                kwargs[name] = None
            elif disposition is not OMIT:
                raise build_arg_error(arg_name=name, item=item)
"""


@dataclasses.dataclass(frozen=True, slots=True)
class _Shape:
    """The parts of a Factory that decide its generated source; factories of one shape share a code object."""

    arity: int
    names: tuple[str, ...] | None
    static: bool
    context: bool
    cached: bool

    def source(self) -> str:
        if self.names is None:
            build = "\n".join(f"        a{i} = r{i}(target)" for i in range(self.arity)) or "        pass"
            args = ", ".join(f"a{i}" for i in range(self.arity))
            built = "(" + "".join(f"a{i}, " for i in range(self.arity)) + ")"
            star = "*"
        else:
            build = (
                "        kwargs = {" + ", ".join(f"{name!r}: r{i}(target)" for i, name in enumerate(self.names)) + "}"
            )
            if self.static:
                build += "\n        kwargs.update(static)"
            if self.context:
                build += "\n" + _CONTEXT_FOLD.rstrip("\n")
            args, built, star = "**kwargs", "kwargs", "**"
        if self.cached:
            return _CACHED.format(build=build, built=built, star=star)
        return _TRANSIENT.format(build=build, args=args)


_shape_ids = itertools.count()


@functools.cache
def _code(shape: _Shape) -> "CodeType":
    source = shape.source()
    filename = f"<modern_di resolver shape {next(_shape_ids)}>"
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    return compile(source, filename, "exec")


def _compile_factory(f: "Factory[typing.Any]", registry: "ProvidersRegistry") -> "Resolver":
    plan = registry.plan_for(f, f._parsed_kwargs, f._kwargs)
    if plan.unwireable:
        return _compile_unwireable_factory(f, plan)
    static = dict(plan.static_kwargs)
    context: list[tuple[typing.Any, ...]] = []
    for name, (context_provider, item) in plan.context_kwargs.items():
        override = registry.overrides.fetch_override(context_provider.provider_id)
        if override is not types.UNSET:
            static[name] = override
        else:
            context.append(
                (name, context_provider.scope, context_provider.context_type, absent_disposition(item), item)
            )
    positional = _can_call_positionally(f, plan)
    shape = _Shape(
        arity=len(plan.provider_kwargs),
        names=None if positional else tuple(plan.provider_kwargs),
        static=bool(static),
        context=bool(context),
        cached=f.cache_settings is not None,
    )
    namespace: dict[str, typing.Any] = {
        "provider": f,
        "pid": f.provider_id,
        "scope": f.scope,
        "creator": f._creator,
        "resolution_step": f._resolution_step,
        "build_arg_error": f._argument_resolution_error,
        "static": static,
        "context": tuple(context),
        "UNSET": types.UNSET,
        "NULL": _Absent.NULL,
        "OMIT": _Absent.OMIT,
        "partial": functools.partial,
        "_navigate": _navigate,
        "_STEP_ERRORS": _STEP_ERRORS,
        "CreatorCallError": exceptions.CreatorCallError,
        **{f"r{i}": registry.resolver_for(p) for i, p in enumerate(plan.provider_kwargs.values())},
    }
    exec(_code(shape), namespace)  # noqa: S102  # the source is a fixed template; user data enters only via `namespace`
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
        if target.closed:
            target._prepare()
        error = build_error(arg_name=arg_name, item=item, registry=target.providers_registry)
        error.prepend_step(resolution_step())
        raise error

    return resolve


def _compile_alias(a: "Alias[typing.Any]") -> "Resolver":
    """Call the source's resolver directly; a source registered later is picked up on the next resolve."""
    # Not bound to the source's resolver at compile time: the alias step in error chains needs this frame.
    source_type = a._source_type
    find_source = a._find_source

    def resolve(container: "Container") -> typing.Any:
        try:
            registry = container.providers_registry
            source = registry._providers.get(source_type)
            if source is None:
                source = find_source(container)
            source_resolver = registry._resolvers.get(source.provider_id)
            if source_resolver is None:
                source_resolver = registry.resolver_for(source)
            return source_resolver(container)
        except _STEP_ERRORS as exc:
            exc.prepend_step(redirect_step(a, container))
            raise

    return resolve


def _resolve_to_container(container: "Container") -> typing.Any:
    return container


def _compile_context_provider(cp: "ContextProvider[typing.Any]") -> "Resolver":
    scope = cp.scope
    context_type = cp.context_type

    def resolve(container: "Container") -> typing.Any:
        target = container if container.scope == scope else container.find_container(scope)
        if target.closed:
            target._prepare()
        value = target.context_registry.find_context(context_type)
        if value is types.UNSET:
            raise exceptions.ContextValueNotSetError(context_type=context_type, scope_name=scope.name)
        return value

    return resolve


def _navigate(
    container: "Container",
    scope: typing.Any,
    resolution_step: "typing.Callable[[], exceptions.ResolutionStep]",
) -> "Container":
    """Cross-scope target lookup; a scope error carries this provider's resolution step."""
    # `find_container`, never an inlined `_scope_map` read: a Container subclass may redirect navigation.
    try:
        return container.find_container(scope)
    except _SCOPE_ERRORS as exc:
        exc.prepend_step(resolution_step())
        raise
