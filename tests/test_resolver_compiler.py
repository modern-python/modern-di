"""Direct tests for compiled-resolver path selection.

The differential-harness suite in ``tests/providers/test_factory.py`` characterizes each
compiled path black-box through ``resolve_provider``. These pin the three things it leaves
unguarded: the argument-ordering invariant the positional fast path silently depends on,
``_can_call_positionally``'s full contract (four exclusion rules plus the positive case)
called directly, and the per-node frame budget the compiled path exists to hold.
"""

import dataclasses
import inspect
import sys
import types as _pytypes
import typing

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.providers import ContextProvider
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.resolver_compiler import _can_call_positionally
from modern_di.wiring import WiringPlan


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class _A:
    pass


class _B:
    pass


class _C:
    pass


class _Req:
    pass


@dataclasses.dataclass(slots=True)
class _Ordered:
    a: _A
    b: _B
    c: _C


def _make(a: _A, b: _B, c: _C) -> _Ordered:
    return _Ordered(a=a, b=b, c=c)


def _plan(registry: ProvidersRegistry, owner: "providers.Factory[object]") -> WiringPlan:
    """Build ``owner``'s wiring plan the way production does (via the registry memo)."""
    return registry.plan_for(owner, owner._parsed_kwargs, owner._kwargs)


@dataclasses.dataclass(slots=True)
class _L0:
    pass


@dataclasses.dataclass(slots=True)
class _L1:
    dep: _L0


@dataclasses.dataclass(slots=True)
class _L2:
    dep: _L1


@dataclasses.dataclass(slots=True)
class _L3:
    dep: _L2


@dataclasses.dataclass(slots=True)
class _L4:
    dep: _L3


@dataclasses.dataclass(slots=True)
class _L5:
    dep: _L4


_CHAIN: tuple[type, ...] = (_L0, _L1, _L2, _L3, _L4, _L5)

#: Python calls one extra chain node costs: its resolver closure, plus its creator.
#: The creator is the user's own object construction and is irreducible; the **1**
#: resolver frame is the budget this module exists to hold. See
#: ``architecture/performance.md``.
#:
#: Before 3.12 each resolver's argument build is a *separate* code object -- the
#: positional path's ``<listcomp>`` and the kwargs path's ``<dictcomp>`` -- so it
#: costs a third frame per node. PEP 709 inlines both from 3.12, which is a real
#: per-version cost difference, not a measurement artifact.
_CALLS_PER_NODE = 2 if sys.version_info >= (3, 12) else 3


def _warm_chain(depth: int) -> "tuple[Container, providers.Factory[typing.Any]]":
    """Build and warm a transient chain of ``depth`` nodes; return it and its root provider."""
    members = {f"p{i}": providers.Factory(creator=node, scope=Scope.APP) for i, node in enumerate(_CHAIN[:depth])}
    group = _pytypes.new_class(f"_Chain{depth}", (Group,), exec_body=lambda ns: ns.update(members))
    container = Container(scope=Scope.APP, groups=[group])
    root = members[f"p{depth - 1}"]
    container.resolve_provider(root)  # compile the whole graph before measuring
    return container, root


def _count_python_calls(fn: "typing.Callable[[], object]") -> int:
    """Count Python-level calls made by ``fn``.

    Uses ``sys.setprofile`` rather than stack-depth sampling so a helper frame that is
    *pushed and popped* during resolution (an extracted override guard, say) is still
    counted -- sampling the depth inside a creator would miss exactly that regression.
    """
    calls = 0

    def profiler(_frame: object, event: str, _arg: object) -> None:
        # pragma: no cover - CPython does not trace inside a profile callback, so coverage
        # cannot see this body. That it runs is exactly what the caller's assertion proves.
        nonlocal calls
        if event == "call":  # pragma: no cover
            calls += 1  # pragma: no cover

    sys.setprofile(profiler)
    try:
        fn()
    finally:
        sys.setprofile(None)
    return calls


# ---------------------------------------------------------------------------
# Ordering invariant — the positional fast path binds args in signature order
# ---------------------------------------------------------------------------


def test_positional_path_binds_args_in_signature_order() -> None:
    # A pure-provider factory is correct under BOTH call conventions, so a behavioral test
    # cannot see which path ran. The self-guard below asserts the selector chose positional;
    # the distinct-typed args then make a misordered `pos` observable (a _A would land in .b).
    class G(Group):
        a = providers.Factory(creator=_A, scope=Scope.APP)
        b = providers.Factory(creator=_B, scope=Scope.APP)
        c = providers.Factory(creator=_C, scope=Scope.APP)
        ordered = providers.Factory(creator=_make, scope=Scope.APP)

    container = Container(groups=[G])
    container.open()
    plan = _plan(container.providers_registry, G.ordered)
    assert _can_call_positionally(G.ordered, plan)  # self-guard: positional path selected

    result = container.resolve(_Ordered)
    assert isinstance(result.a, _A)
    assert isinstance(result.b, _B)
    assert isinstance(result.c, _C)


# ---------------------------------------------------------------------------
# _can_call_positionally — the full predicate contract, called directly
# ---------------------------------------------------------------------------


def test_can_call_positionally_accepts_ordered_provider_signature() -> None:
    # positive: every param is a provider dep in signature order -> the positional path is eligible.
    registry = ProvidersRegistry()
    registry.add_providers(
        providers.Factory(creator=_A, scope=Scope.APP),
        providers.Factory(creator=_B, scope=Scope.APP),
        providers.Factory(creator=_C, scope=Scope.APP),
    )
    owner = providers.Factory(creator=_make, scope=Scope.APP)
    registry.add_providers(owner)

    assert _can_call_positionally(owner, _plan(registry, owner)) is True


def test_can_call_positionally_rejects_static_or_context_kwarg() -> None:
    # rule 1: a context param makes the plan non-pure, so kwargs folding must run.
    def creator(dep: _A, req: _Req) -> _Ordered:
        raise NotImplementedError  # pragma: no cover - parsed for wiring, never resolved

    registry = ProvidersRegistry()
    registry.add_providers(
        providers.Factory(creator=_A, scope=Scope.APP),
        ContextProvider(context_type=_Req, scope=Scope.APP),
    )
    owner = providers.Factory(creator=creator, scope=Scope.APP)
    registry.add_providers(owner)

    assert _can_call_positionally(owner, _plan(registry, owner)) is False


def test_can_call_positionally_rejects_defaulted_omitted_param() -> None:
    # rule 2a: `opt` has a default and no provider, so it is omitted -> provider_kwargs is a
    # strict prefix of the signature, not the whole of it.
    def creator(dep: _A, opt: int = 5) -> _Ordered:
        raise NotImplementedError  # pragma: no cover - parsed for wiring, never resolved

    registry = ProvidersRegistry()
    registry.add_providers(providers.Factory(creator=_A, scope=Scope.APP))
    owner = providers.Factory(creator=creator, scope=Scope.APP)
    registry.add_providers(owner)

    assert _can_call_positionally(owner, _plan(registry, owner)) is False


def test_can_call_positionally_rejects_kwargs_overlay_reorder() -> None:
    # rule 2b: supplying `a` via the kwargs overlay defers it to the end of provider_kwargs,
    # so the binding order (b, a) no longer matches the signature (a, b).
    def creator(a: _A, b: _B) -> _Ordered:
        raise NotImplementedError  # pragma: no cover - parsed for wiring, never resolved

    registry = ProvidersRegistry()
    factory_a = providers.Factory(creator=_A, scope=Scope.APP)
    registry.add_providers(factory_a, providers.Factory(creator=_B, scope=Scope.APP))
    owner = providers.Factory(creator=creator, scope=Scope.APP, kwargs={"a": factory_a})
    registry.add_providers(owner)

    plan = _plan(registry, owner)
    assert tuple(plan.provider_kwargs) == ("b", "a")  # overlay put `a` last
    assert _can_call_positionally(owner, plan) is False


def test_can_call_positionally_rejects_keyword_only_param() -> None:
    # rule 3: a keyword-only dep can never be passed positionally.
    def creator(*, dep: _A) -> _Ordered:
        raise NotImplementedError  # pragma: no cover - parsed for wiring, never resolved

    registry = ProvidersRegistry()
    registry.add_providers(providers.Factory(creator=_A, scope=Scope.APP))
    owner = providers.Factory(creator=creator, scope=Scope.APP)
    registry.add_providers(owner)

    assert _can_call_positionally(owner, _plan(registry, owner)) is False


def test_can_call_positionally_rejects_positional_only_param() -> None:
    # rule 4: `prefix` is positional-only WITH a default, dropped from parsed_kwargs so the
    # remaining names look like a clean prefix ("dep",) -- but a positional call would bind
    # `dep` to the `prefix` slot. The parser's has_positional_only_gap flag must reject it.
    def creator(prefix: str = "P", /, dep: _A = None) -> _Ordered:  # ty: ignore[invalid-parameter-default]
        raise NotImplementedError  # pragma: no cover - parsed for wiring, never resolved

    registry = ProvidersRegistry()
    registry.add_providers(providers.Factory(creator=_A, scope=Scope.APP))
    owner = providers.Factory(creator=creator, scope=Scope.APP)
    registry.add_providers(owner)

    assert _can_call_positionally(owner, _plan(registry, owner)) is False


def test_first_resolve_does_not_reintrospect_creator(monkeypatch: pytest.MonkeyPatch) -> None:
    # Perf guard (audit 2026-07-19 Candidate 1): parse_creator records positional-only params at
    # construction, so the compile-time positional predicate must not re-run inspect.signature.
    class G(Group):
        a = providers.Factory(creator=_A, scope=Scope.APP)
        b = providers.Factory(creator=_B, scope=Scope.APP)
        c = providers.Factory(creator=_C, scope=Scope.APP)
        ordered = providers.Factory(creator=_make, scope=Scope.APP)

    container = Container(groups=[G])  # parse_creator already ran at G's class def
    container.open()
    calls: list[object] = []
    real_signature = inspect.signature

    def _spy(
        obj: object, *args: object, **kwargs: object
    ) -> inspect.Signature:  # pragma: no cover - runs only on regression
        calls.append(obj)
        return real_signature(obj, *args, **kwargs)  # ty: ignore[invalid-argument-type]

    monkeypatch.setattr(inspect, "signature", _spy)
    container.resolve_provider(G.ordered)  # triggers compile of the whole graph
    assert calls == []  # no re-introspection at compile


# ---------------------------------------------------------------------------
# Frame budget — one resolver frame per chain node, and no more
# ---------------------------------------------------------------------------


def test_resolve_costs_exactly_one_resolver_frame_per_node() -> None:
    # Every compiled resolver front-guards its own override, navigates its own scope and
    # inlines its own kwargs build + creator call. That duplication is deliberate: any of it
    # extracted into a shared helper would cost one Python frame *per resolved node*, which
    # is the whole reason the compiled path exists (architecture/performance.md).
    #
    # Measured as a difference between two chain depths, so the fixed cost of the harness
    # and of `resolve_provider` itself cancels and only the per-node slope is asserted.
    shallow_container, shallow_root = _warm_chain(2)
    deep_container, deep_root = _warm_chain(6)

    shallow = _count_python_calls(lambda: shallow_container.resolve_provider(shallow_root))
    deep = _count_python_calls(lambda: deep_container.resolve_provider(deep_root))

    assert (deep - shallow) == (6 - 2) * _CALLS_PER_NODE, (
        f"per-node cost is {(deep - shallow) / (6 - 2)} Python calls, expected {_CALLS_PER_NODE} "
        f"on Python {sys.version_info.major}.{sys.version_info.minor}. A helper extracted from "
        f"the compiled resolvers costs one frame per resolved node -- see architecture/performance.md."
    )


def test_alias_hop_costs_exactly_one_resolver_frame() -> None:
    # An alias forwards to its source's compiled resolver by direct reference, like every
    # Factory dependency. Routing through `_find_source` + `find_provider` +
    # `resolve_provider` instead costs four frames per hop -- see architecture/performance.md.
    class _Source: ...

    class _Iface: ...

    class _Direct(Group):
        source = providers.Factory(creator=_Source, scope=Scope.APP)

    class _Aliased(Group):
        source = providers.Factory(creator=_Source, scope=Scope.APP)
        iface = providers.Alias(source_type=_Source, bound_type=_Iface)

    direct = Container(scope=Scope.APP, groups=[_Direct])
    aliased = Container(scope=Scope.APP, groups=[_Aliased])
    direct.resolve_provider(_Direct.source)  # compile before measuring
    aliased.resolve_provider(_Aliased.iface)

    without_alias = _count_python_calls(lambda: direct.resolve_provider(_Direct.source))
    with_alias = _count_python_calls(lambda: aliased.resolve_provider(_Aliased.iface))

    assert (with_alias - without_alias) == 1, (
        f"an alias hop costs {with_alias - without_alias} Python calls, expected 1 (its own "
        f"resolver). Looking the source up per resolve costs four -- see architecture/performance.md."
    )


def test_overridden_alias_compiles_nothing_of_its_source() -> None:
    # The override front-guard runs before the source is ever looked up, so the mock pattern
    # never pays to compile a subtree it will not touch.
    class _Source: ...

    class _Iface: ...

    class _G(Group):
        source = providers.Factory(creator=_Source, scope=Scope.APP)
        iface = providers.Alias(source_type=_Source, bound_type=_Iface)

    container = Container(scope=Scope.APP, groups=[_G])
    sentinel = object()
    container.override(_G.iface, sentinel)

    assert container.resolve(_Iface) is sentinel
    assert list(container.providers_registry._resolvers) == [_G.iface.provider_id]


def test_no_compiled_resolver_closes_over_its_registry() -> None:
    # A resolver that captures its registry forms a cycle with the memo holding it, so the
    # registry is reclaimable only by cyclic GC. Every closure reads its registries off the
    # container argument instead.
    class _Src: ...

    class _Iface: ...

    class _G(Group):
        source = providers.Factory(creator=_Src, scope=Scope.APP)
        iface = providers.Alias(source_type=_Src, bound_type=_Iface)

    container = Container(scope=Scope.APP, groups=[_G])
    container.resolve(_Iface)
    registry = container.providers_registry

    capturing = [
        fn.__qualname__
        for fn in typing.cast("tuple[_pytypes.FunctionType, ...]", tuple(registry._resolvers.values()))
        for cell in (fn.__closure__ or ())
        if cell.cell_contents is registry
    ]

    assert capturing == []


def test_cached_resolver_has_no_cell_on_the_warm_path() -> None:
    # The cold-miss thunk must not close over `target`: a closure promotes it to a cell, so
    # MAKE_CELL runs in the resolver's prologue on every call -- including the warm hit that
    # returns early, and the override hit that never reaches `target` at all. Measured at ~18 ns
    # of a ~162 ns warm resolve. Nothing else in the suite would catch a revert to a lambda.
    class G(Group):
        cached = providers.Factory(creator=_A, scope=Scope.APP, cache=True)

    container = Container(scope=Scope.APP, groups=[G])
    resolver = container.providers_registry.resolver_for(G.cached)
    code = typing.cast("_pytypes.FunctionType", resolver).__code__

    assert code.co_cellvars == (), (
        f"the cached-factory resolver grew cell variables {code.co_cellvars}; "
        f"a MAKE_CELL now runs on every warm hit -- see architecture/performance.md"
    )
