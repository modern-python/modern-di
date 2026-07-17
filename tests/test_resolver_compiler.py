"""Direct tests for compiled-resolver path selection.

The differential-harness suite in ``tests/providers/test_factory.py`` characterizes each
compiled path black-box through ``resolve_provider``. These pin the two things it leaves
unguarded: the argument-ordering invariant the positional fast path silently depends on,
and ``_positional_names``' full contract (four exclusion rules plus the positive case),
called directly.
"""

import dataclasses

from modern_di import Container, Group, Scope, providers
from modern_di.providers import ContextProvider
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.resolver_compiler import _positional_names
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
    return registry.plan_for(owner, owner._parsed_kwargs, owner._kwargs)  # noqa: SLF001


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

    container = Container(groups=[G], validate=False)
    plan = _plan(container.providers_registry, G.ordered)
    assert _positional_names(G.ordered, plan) is not None  # self-guard: positional path selected

    result = container.resolve(_Ordered)
    assert isinstance(result.a, _A)
    assert isinstance(result.b, _B)
    assert isinstance(result.c, _C)


# ---------------------------------------------------------------------------
# _positional_names — the full predicate contract, called directly
# ---------------------------------------------------------------------------


def test_positional_names_returns_ordered_names() -> None:
    # positive: every param is a provider dep in signature order -> the ordered names tuple.
    registry = ProvidersRegistry()
    registry.add_providers(
        providers.Factory(creator=_A, scope=Scope.APP),
        providers.Factory(creator=_B, scope=Scope.APP),
        providers.Factory(creator=_C, scope=Scope.APP),
    )
    owner = providers.Factory(creator=_make, scope=Scope.APP)
    registry.add_providers(owner)

    assert _positional_names(owner, _plan(registry, owner)) == ("a", "b", "c")


def test_positional_names_rejects_static_or_context_kwarg() -> None:
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

    assert _positional_names(owner, _plan(registry, owner)) is None


def test_positional_names_rejects_defaulted_omitted_param() -> None:
    # rule 2a: `opt` has a default and no provider, so it is omitted -> provider_kwargs is a
    # strict prefix of the signature, not the whole of it.
    def creator(dep: _A, opt: int = 5) -> _Ordered:
        raise NotImplementedError  # pragma: no cover - parsed for wiring, never resolved

    registry = ProvidersRegistry()
    registry.add_providers(providers.Factory(creator=_A, scope=Scope.APP))
    owner = providers.Factory(creator=creator, scope=Scope.APP)
    registry.add_providers(owner)

    assert _positional_names(owner, _plan(registry, owner)) is None


def test_positional_names_rejects_kwargs_overlay_reorder() -> None:
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
    assert _positional_names(owner, plan) is None


def test_positional_names_rejects_keyword_only_param() -> None:
    # rule 3: a keyword-only dep can never be passed positionally.
    def creator(*, dep: _A) -> _Ordered:
        raise NotImplementedError  # pragma: no cover - parsed for wiring, never resolved

    registry = ProvidersRegistry()
    registry.add_providers(providers.Factory(creator=_A, scope=Scope.APP))
    owner = providers.Factory(creator=creator, scope=Scope.APP)
    registry.add_providers(owner)

    assert _positional_names(owner, _plan(registry, owner)) is None


def test_positional_names_rejects_positional_only_param() -> None:
    # rule 4: `prefix` is positional-only WITH a default, dropped from parsed_kwargs so the
    # remaining names look like a clean prefix ("dep",) -- but a positional call would bind
    # `dep` to the `prefix` slot. The raw-signature scan must reject it.
    def creator(prefix: str = "P", /, dep: _A = None) -> _Ordered:  # ty: ignore[invalid-parameter-default]
        raise NotImplementedError  # pragma: no cover - parsed for wiring, never resolved

    registry = ProvidersRegistry()
    registry.add_providers(providers.Factory(creator=_A, scope=Scope.APP))
    owner = providers.Factory(creator=creator, scope=Scope.APP)
    registry.add_providers(owner)

    assert _positional_names(owner, _plan(registry, owner)) is None
