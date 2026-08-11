import dataclasses
import enum

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import (
    InvalidChildScopeError,
    MaxScopeReachedError,
    ScopeNotInitializedError,
    ScopeSkippedError,
)
from modern_di.scope import _deeper_members, _next_deeper


class MyScope(enum.IntEnum):
    TENANT = 6
    BACKGROUND_JOB = 7


class ConflictingScope(enum.IntEnum):
    SAME_AS_APP = 1
    LOWER_THAN_REQUEST = 2


@dataclasses.dataclass(kw_only=True, slots=True)
class TenantService:
    pass


def test_build_child_at_custom_scope_from_step() -> None:
    step_container = Container(scope=Scope.STEP)
    step_container.open()
    tenant_container = step_container.build_child_container(scope=MyScope.TENANT)
    assert tenant_container.scope is MyScope.TENANT
    assert tenant_container.parent_container is step_container


def test_build_child_at_custom_scope_from_app_skips_intermediate() -> None:
    app_container = Container()
    app_container.open()
    tenant_container = app_container.build_child_container(scope=MyScope.TENANT)
    assert tenant_container.scope is MyScope.TENANT


def test_factory_resolves_through_custom_scope_container() -> None:
    class TenantGroup(Group):
        svc = providers.Factory(scope=MyScope.TENANT, creator=TenantService)

    app_container = Container(groups=[TenantGroup])
    app_container.open()
    tenant_container = app_container.build_child_container(scope=MyScope.TENANT)
    tenant_container.open()

    instance = tenant_container.resolve(TenantService)
    assert isinstance(instance, TenantService)


def test_resolve_at_custom_scope_from_app_raises_scope_not_initialized() -> None:
    class TenantGroup(Group):
        svc = providers.Factory(scope=MyScope.TENANT, creator=TenantService)

    app_container = Container(groups=[TenantGroup])
    app_container.open()
    with pytest.raises(ScopeNotInitializedError, match="TENANT") as exc:
        app_container.resolve(TenantService)
    assert exc.value.provider_scope is MyScope.TENANT
    assert exc.value.container_scope is Scope.APP


def test_resolve_app_provider_from_custom_scope_with_skipped_chain() -> None:
    # A standalone tenant container that never went through APP -> ... chain
    tenant_container = Container(scope=MyScope.TENANT)
    tenant_container.open()
    app_factory = providers.Factory(creator=lambda: "x")
    with pytest.raises(ScopeSkippedError, match="APP"):
        tenant_container.resolve_provider(app_factory)


def test_invalid_child_scope_uses_parent_enum_for_allowed_list() -> None:
    tenant_container = Container(scope=MyScope.TENANT)
    tenant_container.open()
    with pytest.raises(InvalidChildScopeError) as exc:
        tenant_container.build_child_container(scope=MyScope.TENANT)
    # allowed_scopes must be drawn from the parent's own enum class (MyScope),
    # not the standard Scope enum.
    assert exc.value.allowed_scopes == ["BACKGROUND_JOB"]


def test_invalid_child_scope_with_conflicting_value() -> None:
    app_container = Container()
    app_container.open()
    with pytest.raises(InvalidChildScopeError) as exc:
        app_container.build_child_container(scope=ConflictingScope.SAME_AS_APP)
    assert exc.value.parent_scope is Scope.APP
    assert exc.value.child_scope is ConflictingScope.SAME_AS_APP


def test_scope_algebra_answers_deeper_members_for_any_int_enum() -> None:
    """INVARIANT: the scope algebra takes any IntEnum, not only `Scope`.

    A custom scope cannot subclass `Scope` (Python forbids extending an enum with members), so an
    algebra expressed as methods on `Scope` would apply to the five built-in members and nothing
    else. Free functions are what make custom scopes work at all.
    """
    assert _deeper_members(MyScope.TENANT) == [MyScope.BACKGROUND_JOB]
    assert _deeper_members(MyScope.BACKGROUND_JOB) == []
    assert _deeper_members(Scope.ACTION) == [Scope.STEP]


def test_scope_algebra_next_deeper_is_the_shallowest_deeper_member() -> None:
    """INVARIANT: `_next_deeper` returns the shallowest deeper member of the provider's own enum.

    Not `value + 1` -- a non-contiguous custom enum (`TENANT=6, JOB=10`) must derive `JOB` from
    `TENANT`. Returning `None` at the deepest member (rather than raising) is what keeps `scope.py`
    from importing `exceptions.py`.
    """
    assert _next_deeper(GappedScope.TENANT) is GappedScope.BACKGROUND_JOB
    assert _next_deeper(Scope.APP) is Scope.SESSION
    assert _next_deeper(GappedScope.BACKGROUND_JOB) is None
    assert _next_deeper(Scope.STEP) is None


def test_caching_isolated_across_tenant_containers() -> None:
    class TenantGroup(Group):
        svc = providers.Factory(
            scope=MyScope.TENANT,
            creator=TenantService,
            cache=True,
        )

    app_container = Container(groups=[TenantGroup])
    app_container.open()
    tenant_a = app_container.build_child_container(scope=MyScope.TENANT)
    tenant_a.open()
    tenant_b = app_container.build_child_container(scope=MyScope.TENANT)
    tenant_b.open()

    instance_a = tenant_a.resolve(TenantService)
    instance_b = tenant_b.resolve(TenantService)
    assert instance_a is not instance_b
    assert tenant_a.resolve(TenantService) is instance_a


def test_auto_derive_within_custom_enum() -> None:
    tenant_container = Container(scope=MyScope.TENANT)
    tenant_container.open()
    bg_container = tenant_container.build_child_container()
    assert bg_container.scope is MyScope.BACKGROUND_JOB


class GappedScope(enum.IntEnum):
    TENANT = 6
    BACKGROUND_JOB = 10


def test_auto_derive_with_gapped_custom_enum() -> None:
    # Non-contiguous values: the next scope is the smallest member greater than the
    # current one, not current.value + 1 (which would not be a valid member).
    tenant_container = Container(scope=GappedScope.TENANT)
    tenant_container.open()
    bg_container = tenant_container.build_child_container()
    assert bg_container.scope is GappedScope.BACKGROUND_JOB


def test_auto_derive_at_deepest_gapped_scope_raises_max() -> None:
    bg_container = Container(scope=GappedScope.BACKGROUND_JOB)
    bg_container.open()
    with pytest.raises(MaxScopeReachedError):
        bg_container.build_child_container()


def test_next_deeper_memo_does_not_collide_across_enums_sharing_a_value() -> None:
    # _next_deeper is memoized. IntEnum members compare/hash by integer value, so MyScope.TENANT
    # and GappedScope.TENANT (both == 6) would collide under a bare-member cache key — the memo
    # keys on (type, member) to keep each enum's own answer. Both orders, to catch either the
    # first or second call being served a foreign result.
    assert _next_deeper(MyScope.TENANT) is MyScope.BACKGROUND_JOB  # 6 -> 7 (contiguous)
    assert _next_deeper(GappedScope.TENANT) is GappedScope.BACKGROUND_JOB  # 6 -> 10 (gapped), not 7


def test_build_child_container_rejects_zero_valued_custom_scope() -> None:
    class ZeroEnum(enum.IntEnum):
        ZERO = 0
        ONE = 1
        TWO = 2

    parent = Container(scope=ZeroEnum.ONE)
    parent.open()
    with pytest.raises(InvalidChildScopeError):
        parent.build_child_container(scope=ZeroEnum.ZERO)
