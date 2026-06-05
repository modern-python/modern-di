import dataclasses
import enum

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import (
    InvalidChildScopeError,
    ScopeNotInitializedError,
    ScopeSkippedError,
)


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
    tenant_container = step_container.build_child_container(scope=MyScope.TENANT)
    assert tenant_container.scope is MyScope.TENANT
    assert tenant_container.parent_container is step_container


def test_build_child_at_custom_scope_from_app_skips_intermediate() -> None:
    app_container = Container()
    tenant_container = app_container.build_child_container(scope=MyScope.TENANT)
    assert tenant_container.scope is MyScope.TENANT


def test_factory_resolves_through_custom_scope_container() -> None:
    class TenantGroup(Group):
        svc = providers.Factory(scope=MyScope.TENANT, creator=TenantService)

    app_container = Container(groups=[TenantGroup])
    tenant_container = app_container.build_child_container(scope=MyScope.TENANT)

    instance = tenant_container.resolve(TenantService)
    assert isinstance(instance, TenantService)


def test_resolve_at_custom_scope_from_app_raises_scope_not_initialized() -> None:
    class TenantGroup(Group):
        svc = providers.Factory(scope=MyScope.TENANT, creator=TenantService)

    app_container = Container(groups=[TenantGroup])
    with pytest.raises(ScopeNotInitializedError, match="TENANT") as exc:
        app_container.resolve(TenantService)
    assert exc.value.provider_scope is MyScope.TENANT
    assert exc.value.container_scope is Scope.APP


def test_resolve_app_provider_from_custom_scope_with_skipped_chain() -> None:
    # A standalone tenant container that never went through APP -> ... chain
    tenant_container = Container(scope=MyScope.TENANT)
    app_factory = providers.Factory(creator=lambda: "x")
    with pytest.raises(ScopeSkippedError, match="APP"):
        tenant_container.resolve_provider(app_factory)


def test_invalid_child_scope_uses_parent_enum_for_allowed_list() -> None:
    tenant_container = Container(scope=MyScope.TENANT)
    with pytest.raises(InvalidChildScopeError) as exc:
        tenant_container.build_child_container(scope=MyScope.TENANT)
    # allowed_scopes must be drawn from the parent's own enum class (MyScope),
    # not the standard Scope enum.
    assert exc.value.allowed_scopes == ["BACKGROUND_JOB"]


def test_invalid_child_scope_with_conflicting_value() -> None:
    app_container = Container()
    with pytest.raises(InvalidChildScopeError) as exc:
        app_container.build_child_container(scope=ConflictingScope.SAME_AS_APP)
    assert exc.value.parent_scope is Scope.APP
    assert exc.value.child_scope is ConflictingScope.SAME_AS_APP


def test_caching_isolated_across_tenant_containers() -> None:
    class TenantGroup(Group):
        svc = providers.Factory(
            scope=MyScope.TENANT,
            creator=TenantService,
            cache_settings=providers.CacheSettings(),
        )

    app_container = Container(groups=[TenantGroup])
    tenant_a = app_container.build_child_container(scope=MyScope.TENANT)
    tenant_b = app_container.build_child_container(scope=MyScope.TENANT)

    instance_a = tenant_a.resolve(TenantService)
    instance_b = tenant_b.resolve(TenantService)
    assert instance_a is not instance_b
    assert tenant_a.resolve(TenantService) is instance_a


def test_auto_derive_within_custom_enum() -> None:
    tenant_container = Container(scope=MyScope.TENANT)
    bg_container = tenant_container.build_child_container()
    assert bg_container.scope is MyScope.BACKGROUND_JOB


def test_build_child_container_rejects_zero_valued_custom_scope() -> None:
    class ZeroEnum(enum.IntEnum):
        ZERO = 0
        ONE = 1
        TWO = 2

    parent = Container(scope=ZeroEnum.ONE)
    with pytest.raises(InvalidChildScopeError):
        parent.build_child_container(scope=ZeroEnum.ZERO)
