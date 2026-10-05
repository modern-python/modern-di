"""Direct tests for WiringPlan.build — no Container required."""

import pytest

from modern_di import providers
from modern_di.providers import ContextProvider
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.scope import Scope
from modern_di.types_parser import SignatureItem
from modern_di.wiring import WiringPlan, find_dep_provider


# ---------------------------------------------------------------------------
# Simple domain types used across tests
# ---------------------------------------------------------------------------


class _ServiceA:
    pass


class _ServiceB:
    pass


class _Request:
    pass


# ---------------------------------------------------------------------------
# Test 1: Partitioning — the bucket kinds across two creators
# ---------------------------------------------------------------------------


class _MultiKindCreator:
    """Creator exercising every wiring bucket.

    a) type-matched provider param  → provider_kwargs
    b) static kwarg literal         → static_kwargs
    c) ContextProvider param        → provider_kwargs, like any other provider
    d) defaulted param (absent)     → omitted from all buckets
    """

    def __init__(
        self,
        svc_a: _ServiceA,
        svc_b: _ServiceB,
        req: _Request,
        with_default: int = 42,
    ) -> None:
        pass  # pragma: no cover - never instantiated; WiringPlan.build only reads its signature


class _NullableNoDefaultCreator:
    """Creator with a nullable param and no default.

    Maps to static_kwargs[k] = None.
    """

    def __init__(self, nullable: str | None) -> None:
        pass  # pragma: no cover - never instantiated; WiringPlan.build only reads its signature


def test_wiring_plan_partitioning() -> None:
    factory_a = providers.Factory(scope=Scope.APP, creator=_ServiceA)
    factory_b = providers.Factory(scope=Scope.APP, creator=_ServiceB)
    ctx_req = ContextProvider(scope=Scope.APP, context_type=_Request)

    registry = ProvidersRegistry()
    registry.add_providers(factory_a, factory_b, ctx_req)

    owner = providers.Factory(
        scope=Scope.APP,
        creator=_MultiKindCreator,
        kwargs={"svc_b": "static-literal"},  # supply svc_b as a static value
    )

    plan = WiringPlan.build(
        owner,
        registry=registry,
    )

    # a) type-matched provider → provider_kwargs
    assert "svc_a" in plan.provider_kwargs
    assert plan.provider_kwargs["svc_a"] is factory_a

    # b) static kwarg literal → static_kwargs
    assert plan.static_kwargs.get("svc_b") == "static-literal"

    # c) ContextProvider param → provider_kwargs, like any other dependency
    assert plan.provider_kwargs["req"] is ctx_req

    # d) defaulted param → omitted from both buckets
    assert "with_default" not in plan.provider_kwargs
    assert "with_default" not in plan.static_kwargs

    # no unwireable params on a correctly wired plan
    assert plan.unwireable == []


def test_wiring_plan_nullable_no_default_goes_to_static_kwargs() -> None:
    # e) nullable param, no default, no registered provider → static_kwargs[k] is None
    registry = ProvidersRegistry()
    owner = providers.Factory(scope=Scope.APP, creator=_NullableNoDefaultCreator)

    plan = WiringPlan.build(
        owner,
        registry=registry,
    )

    assert "nullable" in plan.static_kwargs
    assert plan.static_kwargs["nullable"] is None
    assert plan.unwireable == []


# ---------------------------------------------------------------------------
# Test 2: Issues populated without raising
# ---------------------------------------------------------------------------


class _UnwirableCreator:
    def __init__(self, required_dep: _ServiceA) -> None:
        pass  # pragma: no cover - never instantiated; WiringPlan.build only reads its signature


def test_wiring_plan_unwireable_no_raise() -> None:
    # Empty registry — _ServiceA has no provider
    registry = ProvidersRegistry()
    owner = providers.Factory(scope=Scope.APP, creator=_UnwirableCreator)

    plan = WiringPlan.build(
        owner,
        registry=registry,
    )

    # build returns normally (no raise)
    assert len(plan.unwireable) == 1
    unwired_name, unwired_item = plan.unwireable[0]
    assert unwired_name == "required_dep"
    assert unwired_item.arg_type is _ServiceA

    # nothing wired when the only param is unwirable
    assert plan.provider_kwargs == {}
    assert plan.static_kwargs == {}


# ---------------------------------------------------------------------------
# Test 3: edges include static-supplied providers
# ---------------------------------------------------------------------------


class _MixedOwner:
    def __init__(self, x: _ServiceA, y: _ServiceB) -> None:
        pass  # pragma: no cover - never instantiated; WiringPlan.build only reads its signature


def test_wiring_plan_edges_include_static_supplied_providers() -> None:
    factory_a = providers.Factory(scope=Scope.APP, creator=_ServiceA)
    factory_b = providers.Factory(scope=Scope.APP, creator=_ServiceB)

    registry = ProvidersRegistry()
    registry.add_providers(factory_a, factory_b)

    # Supply `x` via kwargs as a provider reference (static overlay, not type-matched)
    owner = providers.Factory(
        scope=Scope.APP,
        creator=_MixedOwner,
        kwargs={"x": factory_a},
    )

    plan = WiringPlan.build(
        owner,
        registry=registry,
    )

    # `x` is supplied via the kwargs overlay: resolved live AND visible to validate().
    assert "x" in plan.provider_kwargs
    assert plan.provider_kwargs["x"] is factory_a

    # `y` is type-matched → an edge like any other.
    assert plan.provider_kwargs["y"] is factory_b

    # The edge set is exactly what the runtime resolves — however the edge was declared.
    assert set(plan.provider_kwargs) == {"x", "y"}

    assert plan.unwireable == []


# ---------------------------------------------------------------------------
# Test 4: a parameter with no provider — default, then nullable, then unwireable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        # default present (even if also nullable) → omitted (default wins)
        (SignatureItem(default=0, is_nullable=True), "omitted"),
        (SignatureItem(default="x"), "omitted"),
        # no default, nullable → None
        (SignatureItem(is_nullable=True), "none"),
        # no default, not nullable → unwireable
        (SignatureItem(arg_type=int), "unwireable"),
        (SignatureItem(), "unwireable"),
    ],
)
def test_parameter_without_provider_precedence(item: SignatureItem, expected: str) -> None:
    owner = providers.Factory(scope=Scope.APP, creator=_ServiceA)
    owner._params = {"p": item}
    plan = WiringPlan.build(owner, registry=ProvidersRegistry())
    outcome = {
        "omitted": ({}, {}, []),
        "none": ({}, {"p": None}, []),
        "unwireable": ({}, {}, [("p", item)]),
    }[expected]
    assert (plan.provider_kwargs, plan.static_kwargs, plan.unwireable) == outcome


# ---------------------------------------------------------------------------
# Test: default-present overrides nullable (extra precision for the omitted branch)
# ---------------------------------------------------------------------------


def test_parameter_without_provider_default_wins_over_nullable() -> None:
    owner = providers.Factory(scope=Scope.APP, creator=_ServiceA)
    item = SignatureItem(default=None, is_nullable=True)
    owner._params = {"p": item}
    plan = WiringPlan.build(owner, registry=ProvidersRegistry())
    # default is not UNSET (it is None), so omitted regardless of is_nullable
    assert plan.static_kwargs == {}
    assert plan.unwireable == []


# ---------------------------------------------------------------------------
# Test: find_dep_provider, union-members branch (arg_type is None)
# ---------------------------------------------------------------------------


class _UnionTypeA:
    pass


class _UnionTypeB:
    pass


def test_find_dep_provider_union_members_matches_first_registered() -> None:
    """When arg_type is None (union member), find_dep_provider falls through to member_types.

    A SignatureItem with member_types=[_UnionTypeA, _UnionTypeB] and no arg_type (the
    union-member branch) should resolve to the provider registered for the first
    matching member — and appear in provider_kwargs/dependencies accordingly.
    """
    factory_a = providers.Factory(scope=Scope.APP, creator=_UnionTypeA)
    registry = ProvidersRegistry()
    registry.add_providers(factory_a)

    owner = providers.Factory(scope=Scope.APP, creator=_UnionTypeA)

    # Manually craft a SignatureItem with member_types but no arg_type (union member scenario)
    item = SignatureItem(arg_type=None, member_types=[_UnionTypeA, _UnionTypeB])

    result = find_dep_provider(registry, owner, item)
    # factory_a is registered for _UnionTypeA; it is not `owner`, so it must be returned
    assert result is factory_a


def test_find_dep_provider_union_members_skips_owner() -> None:
    """When the only union member matching a registered provider IS the owner, returns None."""
    factory_a = providers.Factory(scope=Scope.APP, creator=_UnionTypeA)
    registry = ProvidersRegistry()
    registry.add_providers(factory_a)

    # owner IS factory_a — should be skipped
    item = SignatureItem(arg_type=None, member_types=[_UnionTypeA])
    result = find_dep_provider(registry, factory_a, item)
    assert result is None


class _OrderedDeps:
    def __init__(self, first: _ServiceA, second: _ServiceB, third: _Request) -> None:
        pass  # pragma: no cover - never instantiated; WiringPlan.build only reads its signature


def test_provider_kwargs_preserves_signature_order() -> None:
    """provider_kwargs iterates in signature order — the invariant the positional fast path depends on.

    _can_call_positionally gates on tuple(provider_kwargs) == tuple(params), then the resolver
    builds its positional tuple from provider_kwargs. If build stopped preserving order, the gate
    would silently de-select the positional path.
    """
    registry = ProvidersRegistry()
    registry.add_providers(
        providers.Factory(scope=Scope.APP, creator=_ServiceA),
        providers.Factory(scope=Scope.APP, creator=_ServiceB),
        providers.Factory(scope=Scope.APP, creator=_Request),
    )
    owner = providers.Factory(scope=Scope.APP, creator=_OrderedDeps)

    plan = WiringPlan.build(
        owner,
        registry=registry,
    )

    assert tuple(plan.provider_kwargs) == ("first", "second", "third")
    assert tuple(plan.provider_kwargs) == tuple(owner._params)
