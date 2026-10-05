import ast
import dataclasses
import enum
import pathlib
import types
import typing

import pytest

import modern_di._scope_algebra
import modern_di.scope
from modern_di import Container, Group, Scope, providers
from modern_di._scope_algebra import deeper_members, next_deeper
from modern_di.exceptions import (
    InvalidChildScopeError,
    InvalidScopeDependencyError,
    MaxScopeReachedError,
    ScopeEnumMismatchError,
    ScopeNotInitializedError,
    ScopeSkippedError,
    ValidationFailedError,
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


def test_scope_algebra_answers_deeper_members_for_any_int_enum() -> None:
    """INVARIANT: the scope algebra takes any IntEnum, not only `Scope`.

    A custom scope cannot subclass `Scope` (Python forbids extending an enum with members), so an
    algebra expressed as methods on `Scope` would apply to the five built-in members and nothing
    else. Free functions are what make custom scopes work at all.
    """
    assert deeper_members(MyScope.TENANT) == [MyScope.BACKGROUND_JOB]
    assert deeper_members(MyScope.BACKGROUND_JOB) == []
    assert deeper_members(Scope.ACTION) == [Scope.STEP]


def test_scope_algebra_next_deeper_is_the_shallowest_deeper_member() -> None:
    """INVARIANT: `next_deeper` returns the shallowest deeper member of the provider's own enum.

    Not `value + 1` -- a non-contiguous custom enum (`TENANT=6, JOB=10`) must derive `JOB` from
    `TENANT`. Returning `None` at the deepest member (rather than raising) is what keeps `_scope_algebra.py`
    from importing `exceptions`.
    """
    assert next_deeper(GappedScope.TENANT) is GappedScope.BACKGROUND_JOB
    assert next_deeper(Scope.APP) is Scope.SESSION
    assert next_deeper(GappedScope.BACKGROUND_JOB) is None
    assert next_deeper(Scope.STEP) is None


def test_caching_isolated_across_tenant_containers() -> None:
    class TenantGroup(Group):
        svc = providers.Factory(
            scope=MyScope.TENANT,
            creator=TenantService,
            cache=True,
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


class GappedScope(enum.IntEnum):
    TENANT = 6
    BACKGROUND_JOB = 10


def test_auto_derive_with_gapped_custom_enum() -> None:
    # Non-contiguous values: the next scope is the smallest member greater than the
    # current one, not current.value + 1 (which would not be a valid member).
    tenant_container = Container(scope=GappedScope.TENANT)
    bg_container = tenant_container.build_child_container()
    assert bg_container.scope is GappedScope.BACKGROUND_JOB


def test_auto_derive_at_deepest_gapped_scope_raises_max() -> None:
    bg_container = Container(scope=GappedScope.BACKGROUND_JOB)
    with pytest.raises(MaxScopeReachedError):
        bg_container.build_child_container()


def test_next_deeper_memo_does_not_collide_across_enums_sharing_a_value() -> None:
    # next_deeper is memoized. IntEnum members compare/hash by integer value, so MyScope.TENANT
    # and GappedScope.TENANT (both == 6) would collide under a bare-member cache key — the memo
    # keys on (type, member) to keep each enum's own answer. Both orders, to catch either the
    # first or second call being served a foreign result.
    assert next_deeper(MyScope.TENANT) is MyScope.BACKGROUND_JOB  # 6 -> 7 (contiguous)
    assert next_deeper(GappedScope.TENANT) is GappedScope.BACKGROUND_JOB  # 6 -> 10 (gapped), not 7


def test_build_child_container_rejects_zero_valued_custom_scope() -> None:
    class ZeroEnum(enum.IntEnum):
        ZERO = 0
        ONE = 1
        TWO = 2

    parent = Container(scope=ZeroEnum.ONE)
    with pytest.raises(InvalidChildScopeError):
        parent.build_child_container(scope=ZeroEnum.ZERO)


def _module_level_imports(source: str) -> set[str]:
    """Top-level module names `source` imports, from both `import x` and `from x import y`.

    A relative `from . import y` parses to `ImportFrom(module=None, level=1, ...)` -- `node.module`
    is `None`, so that case falls back to the names in `node.names` themselves rather than
    silently dropping the import (which would let a `from . import exceptions` pass unnoticed).
    """
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
            else:
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
    return imported


@pytest.mark.parametrize("module", [modern_di.scope, modern_di._scope_algebra])
def test_scope_modules_import_only_enum(module: types.ModuleType) -> None:
    """INVARIANT: `modern_di/scope.py` and `modern_di/_scope_algebra.py` import nothing but `enum`.

    `exceptions/container.py` imports `deeper_members` to derive `InvalidChildScopeError.allowed_scopes`,
    so a scope module that imported `exceptions` would cycle. That is why `next_deeper` returns `None`
    at the deepest member instead of raising `MaxScopeReachedError` itself.
    """
    source = pathlib.Path(typing.cast("str", module.__file__)).read_text(encoding="utf-8")
    imported = _module_level_imports(source)
    assert imported == {"enum"}, f"{module.__name__} grew imports: {sorted(imported)}"

    # Prove the extractor itself would catch a relative import of the forbidden dependency -- the
    # assertion above is only trustworthy if this branch is real, not a no-op.
    assert _module_level_imports("from . import exceptions\n") == {"exceptions"}
    # And the absolute `from x import y` form, so both `ImportFrom` branches are genuinely exercised.
    assert _module_level_imports("from enum import IntEnum\n") == {"enum"}


class _Unregistered: ...


@dataclasses.dataclass(kw_only=True, slots=True)
class _NeedsUnregistered:
    dep: _Unregistered


@pytest.mark.parametrize("cache", [False, True])
def test_same_valued_scope_of_another_enum_does_not_resolve_in_this_container(cache: bool) -> None:
    class ConflictingGroup(Group):
        svc = providers.Factory(scope=ConflictingScope.LOWER_THAN_REQUEST, creator=TenantService, cache=cache)

    session = Container(groups=[ConflictingGroup]).build_child_container(scope=Scope.SESSION)
    with pytest.raises(ScopeSkippedError, match="LOWER_THAN_REQUEST") as exc:
        session.resolve(TenantService)
    assert exc.value.provider_scope is ConflictingScope.LOWER_THAN_REQUEST
    assert exc.value.dependency_path[0].scope is ConflictingScope.LOWER_THAN_REQUEST
    assert session._cache_registry.cached_count() == 0


@pytest.mark.parametrize("cache", [False, True])
def test_same_valued_ancestor_of_another_enum_does_not_resolve(cache: bool) -> None:
    class ConflictingGroup(Group):
        svc = providers.Factory(scope=ConflictingScope.LOWER_THAN_REQUEST, creator=TenantService, cache=cache)

    session = Container(groups=[ConflictingGroup]).build_child_container(scope=Scope.SESSION)
    request = session.build_child_container(scope=Scope.REQUEST)
    with pytest.raises(ScopeSkippedError, match="LOWER_THAN_REQUEST") as exc:
        request.resolve(TenantService)
    assert exc.value.provider_scope is ConflictingScope.LOWER_THAN_REQUEST
    assert exc.value.dependency_path[0].scope is ConflictingScope.LOWER_THAN_REQUEST
    assert session._cache_registry.cached_count() == 0


@pytest.mark.parametrize("scope", [Scope.SESSION, Scope.REQUEST], ids=["SESSION", "REQUEST"])
def test_context_provider_ignores_same_valued_scope_of_another_enum(scope: Scope) -> None:
    class ConflictingGroup(Group):
        ctx = providers.ContextProvider(TenantService, scope=ConflictingScope.LOWER_THAN_REQUEST)

    session = Container(groups=[ConflictingGroup]).build_child_container(
        scope=Scope.SESSION, context={TenantService: TenantService()}
    )
    container = session if scope is Scope.SESSION else session.build_child_container(scope=scope)
    with pytest.raises(ScopeSkippedError, match="LOWER_THAN_REQUEST"):
        container.resolve(TenantService)


def test_unwireable_factory_ignores_same_valued_scope_of_another_enum() -> None:
    class ConflictingGroup(Group):
        svc = providers.Factory(scope=ConflictingScope.LOWER_THAN_REQUEST, creator=_NeedsUnregistered)

    session = Container(groups=[ConflictingGroup]).build_child_container(scope=Scope.SESSION)
    with pytest.raises(ScopeSkippedError, match="LOWER_THAN_REQUEST"):
        session.resolve(_NeedsUnregistered)


def test_find_container_matches_the_enum_member_not_its_value() -> None:
    session = Container().build_child_container(scope=Scope.SESSION)
    request = session.build_child_container(scope=Scope.REQUEST)
    assert request.find_container(Scope.SESSION) is session
    with pytest.raises(ScopeSkippedError):
        session.find_container(ConflictingScope.LOWER_THAN_REQUEST)
    with pytest.raises(ScopeSkippedError):
        request.find_container(ConflictingScope.LOWER_THAN_REQUEST)


@dataclasses.dataclass(kw_only=True, slots=True)
class _AppSettings:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class _TenantRepo:
    settings: _AppSettings


def test_documented_mixed_enum_tree_resolves() -> None:
    class MixedGroup(Group):
        settings = providers.Factory(creator=_AppSettings, cache=True)
        repo = providers.Factory(creator=_TenantRepo, scope=MyScope.TENANT, cache=True)

    app_container = Container(groups=[MixedGroup])
    app_container.validate()
    with app_container.build_child_container(scope=MyScope.TENANT) as tenant_container:
        repo = tenant_container.resolve(_TenantRepo)
        assert tenant_container.resolve(_TenantRepo) is repo
        assert repo.settings is app_container.resolve(_AppSettings)


@dataclasses.dataclass(kw_only=True, slots=True)
class _Session:
    service: TenantService


def test_validate_reports_dependency_on_same_valued_scope_of_another_enum() -> None:
    class MismatchGroup(Group):
        service = providers.Factory(scope=ConflictingScope.LOWER_THAN_REQUEST, creator=TenantService)
        session = providers.Factory(scope=Scope.SESSION, creator=_Session)

    container = Container(groups=[MismatchGroup])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    (issue,) = exc.value.errors
    assert isinstance(issue, ScopeEnumMismatchError)
    assert issue.provider is MismatchGroup.session
    assert issue.parameter_name == "service"
    assert issue.dep_chain == [MismatchGroup.service]


def test_validate_accepts_dependency_on_shallower_scope_of_another_enum() -> None:
    class MixedGroup(Group):
        service = providers.Factory(scope=ConflictingScope.LOWER_THAN_REQUEST, creator=TenantService)
        session = providers.Factory(scope=Scope.REQUEST, creator=_Session)

    app_container = Container(groups=[MixedGroup])
    app_container.validate()
    middle = app_container.build_child_container(scope=ConflictingScope.LOWER_THAN_REQUEST)
    request = middle.build_child_container(scope=Scope.REQUEST)
    assert isinstance(request.resolve(_Session).service, TenantService)


def test_validate_keeps_reporting_a_deeper_scope_of_another_enum_as_invalid_scope_dependency() -> None:
    class DeeperGroup(Group):
        service = providers.Factory(scope=ConflictingScope.LOWER_THAN_REQUEST, creator=TenantService)
        session = providers.Factory(scope=Scope.APP, creator=_Session)

    with pytest.raises(ValidationFailedError) as exc:
        Container(groups=[DeeperGroup]).validate()
    (issue,) = exc.value.errors
    assert isinstance(issue, InvalidScopeDependencyError)
