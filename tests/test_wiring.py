"""Direct tests for WiringPlan.build and absent_disposition — no Container required."""

import pytest

from modern_di import providers
from modern_di.providers import ContextProvider
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.scope import Scope
from modern_di.types import UNSET
from modern_di.types_parser import SignatureItem
from modern_di.wiring import WiringPlan, _Absent, absent_disposition, find_dep_provider


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
# Test 1: Partitioning — five bucket kinds across two creators
# ---------------------------------------------------------------------------


class _MultiKindCreator:
    """Creator exercising four wiring buckets.

    a) type-matched provider param  → provider_kwargs
    b) static kwarg literal         → static_kwargs
    c) ContextProvider param        → context_kwargs
    d) defaulted param (absent)     → omitted from all buckets
    """

    def __init__(
        self,
        svc_a: _ServiceA,
        svc_b: _ServiceB,
        req: _Request,
        with_default: int = 42,
    ) -> None:
        pass  # pragma: no cover


class _NullableNoDefaultCreator:
    """Creator with a nullable param and no default.

    Maps to static_kwargs[k] = None (the NULL disposition).
    """

    def __init__(self, nullable: str | None) -> None:
        pass  # pragma: no cover


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
        parsed_kwargs=owner._parsed_kwargs,  # noqa: SLF001
        kwargs=owner._kwargs,  # noqa: SLF001
        registry=registry,
        owner=owner,
    )

    # a) type-matched provider → provider_kwargs
    assert "svc_a" in plan.provider_kwargs
    assert plan.provider_kwargs["svc_a"] is factory_a

    # b) static kwarg literal → static_kwargs
    assert plan.static_kwargs.get("svc_b") == "static-literal"

    # c) ContextProvider param → context_kwargs
    assert "req" in plan.context_kwargs
    assert plan.context_kwargs["req"][0] is ctx_req

    # d) defaulted param → omitted from all three buckets
    assert "with_default" not in plan.provider_kwargs
    assert "with_default" not in plan.static_kwargs
    assert "with_default" not in plan.context_kwargs

    # no unwireable params on a correctly wired plan
    assert plan.unwireable == []


def test_wiring_plan_nullable_no_default_goes_to_static_kwargs() -> None:
    # e) nullable param, no default, no registered provider → static_kwargs[k] is None
    registry = ProvidersRegistry()
    owner = providers.Factory(scope=Scope.APP, creator=_NullableNoDefaultCreator)

    plan = WiringPlan.build(
        parsed_kwargs=owner._parsed_kwargs,  # noqa: SLF001
        kwargs=None,
        registry=registry,
        owner=owner,
    )

    assert "nullable" in plan.static_kwargs
    assert plan.static_kwargs["nullable"] is None
    assert plan.unwireable == []


# ---------------------------------------------------------------------------
# Test 2: Issues populated without raising
# ---------------------------------------------------------------------------


class _UnwirableCreator:
    def __init__(self, required_dep: _ServiceA) -> None:
        pass  # pragma: no cover


def test_wiring_plan_unwireable_no_raise() -> None:
    # Empty registry — _ServiceA has no provider
    registry = ProvidersRegistry()
    owner = providers.Factory(scope=Scope.APP, creator=_UnwirableCreator)

    plan = WiringPlan.build(
        parsed_kwargs=owner._parsed_kwargs,  # noqa: SLF001
        kwargs=None,
        registry=registry,
        owner=owner,
    )

    # build returns normally (no raise)
    assert len(plan.unwireable) == 1
    unwired_name, unwired_item = plan.unwireable[0]
    assert unwired_name == "required_dep"
    assert unwired_item.arg_type is _ServiceA

    # nothing wired when the only param is unwirable
    assert plan.provider_kwargs == {}
    assert plan.static_kwargs == {}
    assert plan.context_kwargs == {}


# ---------------------------------------------------------------------------
# Test 3: edges include static-supplied providers
# ---------------------------------------------------------------------------


class _MixedOwner:
    def __init__(self, x: _ServiceA, y: _ServiceB) -> None:
        pass  # pragma: no cover


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
        parsed_kwargs=owner._parsed_kwargs,  # noqa: SLF001
        kwargs=owner._kwargs,  # noqa: SLF001
        registry=registry,
        owner=owner,
    )

    # `x` is supplied via the kwargs overlay: resolved live AND visible to validate().
    assert "x" in plan.provider_kwargs
    assert plan.edges["x"] is factory_a

    # `y` is type-matched → an edge like any other.
    assert plan.edges["y"] is factory_b

    # The edge set is exactly what the runtime resolves — however the edge was declared.
    assert set(plan.edges) == {"x", "y"}

    assert plan.unwireable == []


# ---------------------------------------------------------------------------
# Test 4: absent_disposition precedence — parametrized table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        # default present (even if also nullable) → OMIT (default wins)
        (SignatureItem(default=0, is_nullable=True), _Absent.OMIT),
        (SignatureItem(default="x"), _Absent.OMIT),
        # no default, nullable → NULL
        (SignatureItem(is_nullable=True), _Absent.NULL),
        # no default, not nullable → UNWIRABLE
        (SignatureItem(arg_type=int), _Absent.UNWIRABLE),
        (SignatureItem(), _Absent.UNWIRABLE),
    ],
)
def test_absent_disposition_precedence(item: SignatureItem, expected: _Absent) -> None:
    assert absent_disposition(item) is expected


# ---------------------------------------------------------------------------
# Test: default-present overrides nullable (extra precision for the OMIT branch)
# ---------------------------------------------------------------------------


def test_absent_disposition_default_wins_over_nullable() -> None:
    item = SignatureItem(default=None, is_nullable=True)
    # default is not UNSET (it is None), so OMIT regardless of is_nullable
    assert item.default is not UNSET
    assert absent_disposition(item) is _Absent.OMIT


# ---------------------------------------------------------------------------
# Test: find_dep_provider — union-args branch (arg_type is None)
# ---------------------------------------------------------------------------


class _UnionTypeA:
    pass


class _UnionTypeB:
    pass


def test_find_dep_provider_union_args_matches_first_registered() -> None:
    """When arg_type is None (union member), find_dep_provider falls through to args list.

    A SignatureItem with args=[_UnionTypeA, _UnionTypeB] and no arg_type (the
    union-member branch) should resolve to the provider registered for the first
    matching member — and appear in provider_kwargs/dependencies accordingly.
    """
    factory_a = providers.Factory(scope=Scope.APP, creator=_UnionTypeA)
    registry = ProvidersRegistry()
    registry.add_providers(factory_a)

    owner = providers.Factory(scope=Scope.APP, creator=_UnionTypeA)

    # Manually craft a SignatureItem with args but no arg_type (union member scenario)
    item = SignatureItem(arg_type=None, args=[_UnionTypeA, _UnionTypeB])

    result = find_dep_provider(registry, owner, item)
    # factory_a is registered for _UnionTypeA; it is not `owner`, so it must be returned
    assert result is factory_a


def test_find_dep_provider_union_args_skips_owner() -> None:
    """When the only union member matching a registered provider IS the owner, returns None."""
    factory_a = providers.Factory(scope=Scope.APP, creator=_UnionTypeA)
    registry = ProvidersRegistry()
    registry.add_providers(factory_a)

    # owner IS factory_a — should be skipped
    item = SignatureItem(arg_type=None, args=[_UnionTypeA])
    result = find_dep_provider(registry, factory_a, item)
    assert result is None


class _OrderedDeps:
    def __init__(self, first: _ServiceA, second: _ServiceB, third: _Request) -> None:
        pass  # pragma: no cover


def test_provider_kwargs_preserves_signature_order() -> None:
    """provider_kwargs iterates in signature order — the invariant the positional fast path depends on.

    _positional_names gates on tuple(provider_kwargs) == tuple(parsed_kwargs), then the resolver
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
        parsed_kwargs=owner._parsed_kwargs,  # noqa: SLF001
        kwargs=owner._kwargs,  # noqa: SLF001
        registry=registry,
        owner=owner,
    )

    assert tuple(plan.provider_kwargs) == ("first", "second", "third")
    assert tuple(plan.provider_kwargs) == tuple(owner._parsed_kwargs)  # noqa: SLF001
