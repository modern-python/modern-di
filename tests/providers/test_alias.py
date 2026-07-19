import dataclasses

import pytest

from modern_di import Container, Group, Scope, exceptions, providers
from modern_di.dependency_graph import DependencyGraph
from modern_di.exceptions import (
    AliasSourceNotRegisteredError,
    CircularDependencyError,
    ScopeNotInitializedError,
    ValidationFailedError,
)


class AbstractRepository: ...


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class PostgresRepository(AbstractRepository):
    dsn: str = "postgres://localhost"


class MyGroup(Group):
    repo = providers.Factory(creator=PostgresRepository, cache=True)
    abstract_repo = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)


def test_alias_delegates_to_source() -> None:
    container = Container(groups=[MyGroup], validate=True)
    container.open()
    concrete = container.resolve(PostgresRepository)
    abstract = container.resolve(AbstractRepository)
    assert isinstance(abstract, PostgresRepository)
    assert concrete is abstract


def test_alias_without_caching_returns_fresh_instance_per_call() -> None:
    class G(Group):
        repo = providers.Factory(creator=PostgresRepository)
        abstract = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)

    container = Container(groups=[G])
    container.open()
    a = container.resolve(AbstractRepository)
    b = container.resolve(PostgresRepository)
    assert isinstance(a, PostgresRepository)
    assert isinstance(b, PostgresRepository)
    assert a is not b


def test_alias_respects_source_scope() -> None:
    class G(Group):
        repo = providers.Factory(scope=Scope.REQUEST, creator=PostgresRepository)
        abstract = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)

    app_container = Container(groups=[G])
    app_container.open()
    with pytest.raises(ScopeNotInitializedError):
        app_container.resolve(AbstractRepository)

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.open()
    instance = request_container.resolve(AbstractRepository)
    assert isinstance(instance, PostgresRepository)


def test_alias_override_does_not_affect_source() -> None:
    container = Container(groups=[MyGroup])
    container.open()
    mock = PostgresRepository(dsn="mock-alias")
    container.override(MyGroup.abstract_repo, mock)

    assert container.resolve(AbstractRepository) is mock
    assert container.resolve(PostgresRepository) is not mock


def test_source_override_propagates_through_alias() -> None:
    container = Container(groups=[MyGroup])
    container.open()
    mock = PostgresRepository(dsn="mock-source")
    container.override(MyGroup.repo, mock)

    assert container.resolve(PostgresRepository) is mock
    assert container.resolve(AbstractRepository) is mock


def test_alias_missing_source_raises_on_resolve() -> None:
    class G(Group):
        abstract = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)

    # validate=False: this exercises the resolve-time dangling-source error, not deferred validation.
    container = Container(groups=[G], validate=False)
    container.open()
    with pytest.raises(AliasSourceNotRegisteredError, match="PostgresRepository") as exc:
        container.resolve(AbstractRepository)
    assert exc.value.source_type is PostgresRepository


def test_alias_missing_source_raises_on_validate_provider() -> None:
    class G(Group):
        abstract = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)

    container = Container(groups=[G], validate=False)
    container.open()
    with pytest.raises(AliasSourceNotRegisteredError, match="PostgresRepository"):
        container.resolve_provider(G.abstract)


def test_alias_participates_in_cycle_detection() -> None:
    class Iface: ...

    @dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
    class Concrete(Iface):
        dep: Iface

    class G(Group):
        concrete = providers.Factory(creator=Concrete)
        iface_alias = providers.Alias(source_type=Concrete, bound_type=Iface)

    container = Container(groups=[G], validate=True)
    with pytest.raises(ValidationFailedError) as exc:
        container.open()  # deferred validation runs at entry
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)
    assert "Concrete" in str(issue)


def test_alias_default_bound_type_is_source_type() -> None:
    alias = providers.Alias(source_type=PostgresRepository)
    assert alias.bound_type is PostgresRepository


def test_alias_repr() -> None:
    alias = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)
    assert repr(alias) == (
        f"Alias(source_type={PostgresRepository!r}, bound_type={AbstractRepository!r}, scope=<Scope.APP: 1>)"
    )


def test_alias_has_no_definition_site() -> None:
    alias = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)
    assert alias.definition_site is None


class _NotRegisteredSource: ...


class _AliasTarget: ...


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class _NeedsUnregistered:
    dep: _NotRegisteredSource


class _DanglingAliasGroup(Group):
    dangling = providers.Alias(source_type=_NotRegisteredSource, bound_type=_AliasTarget)
    broken_factory = providers.Factory(creator=_NeedsUnregistered)


def test_validate_aggregates_dangling_alias_into_validation_failed_error() -> None:
    container = Container(scope=Scope.APP, groups=[_DanglingAliasGroup], validate=True)
    with pytest.raises(ValidationFailedError) as exc_info:
        container.open()  # deferred validation runs at entry
    errors = exc_info.value.errors
    assert any(isinstance(e, AliasSourceNotRegisteredError) for e in errors)
    min_expected_errors = 2
    assert len(errors) >= min_expected_errors, "validate() must aggregate all issues, not stop at the first"


# Q-13 + Q-14 — alias chains and child→APP-cache identity


class _ChainImpl: ...


class _ChainIfA: ...


class _ChainIfB: ...


class _ChainGroup(Group):
    impl = providers.Factory(scope=Scope.APP, creator=_ChainImpl, cache=True)
    if_a = providers.Alias(source_type=_ChainImpl, bound_type=_ChainIfA)
    if_b = providers.Alias(source_type=_ChainIfA, bound_type=_ChainIfB)


def test_alias_of_alias_resolves_to_source_and_validates() -> None:
    # all alias sources registered, so B-5 validate aggregation is not in play
    container = Container(scope=Scope.APP, groups=[_ChainGroup], validate=True)
    container.open()
    impl = container.resolve(_ChainImpl)
    assert container.resolve(_ChainIfB) is impl
    assert container.resolve(_ChainIfA) is impl


def test_alias_resolved_from_child_returns_app_cached_singleton() -> None:
    container = Container(scope=Scope.APP, groups=[_ChainGroup])
    container.open()
    app_instance = container.resolve(_ChainImpl)
    request = container.build_child_container(scope=Scope.REQUEST)
    request.open()
    assert request.resolve(_ChainIfA) is app_instance


# X-4 — Alias.scope is decorative; validate() must not flag alias->source on scope ordering


class _DeepImpl: ...


class _ShallowIface: ...


class _AliasScopeGroup(Group):
    impl = providers.Factory(scope=Scope.REQUEST, creator=_DeepImpl)
    iface = providers.Alias(source_type=_DeepImpl, bound_type=_ShallowIface)  # default APP scope, shallower than source


def test_validate_does_not_flag_alias_whose_scope_is_shallower_than_source() -> None:
    app = Container(scope=Scope.APP, groups=[_AliasScopeGroup])
    app.open()
    app.validate()  # must NOT raise for the alias->impl edge
    request = app.build_child_container(scope=Scope.REQUEST)
    request.open()
    assert isinstance(request.resolve(_ShallowIface), _DeepImpl)  # resolution works


# X-5 — Alias prepends a resolution step so alias type appears in error chains


class _MissingForAlias: ...


class _AliasTargetIface: ...


@dataclasses.dataclass
class _NeedsMissing:
    x: _MissingForAlias


class _AliasChainErrGroup(Group):
    impl = providers.Factory(scope=Scope.APP, creator=_NeedsMissing)  # _MissingForAlias NOT registered
    iface = providers.Alias(source_type=_NeedsMissing, bound_type=_AliasTargetIface)


def test_alias_appears_in_resolution_error_chain() -> None:
    container = Container(scope=Scope.APP, groups=[_AliasChainErrGroup], validate=False)
    container.open()
    with pytest.raises(exceptions.ArgumentResolutionError) as exc_info:
        container.resolve(_AliasTargetIface)
    rendered = str(exc_info.value)
    assert "_AliasTargetIface" in rendered  # the alias hop appears in the chain


class _MissingForNullAlias: ...


@dataclasses.dataclass
class _NeedsForNullAlias:
    x: _MissingForNullAlias


class _NullBoundAliasGroup(Group):
    impl = providers.Factory(scope=Scope.APP, creator=_NeedsForNullAlias)  # _MissingForNullAlias NOT registered
    iface = providers.Alias(source_type=_NeedsForNullAlias, bound_type=None)  # bound_type=None branch


def test_alias_null_bound_type_resolution_error_uses_repr_fallback() -> None:
    container = Container(scope=Scope.APP, groups=[_NullBoundAliasGroup], validate=False)
    container.open()
    with pytest.raises(exceptions.ArgumentResolutionError) as exc_info:
        container.resolve_provider(_NullBoundAliasGroup.iface)
    rendered = str(exc_info.value)
    assert "Alias(" in rendered  # repr fallback appears in the chain


class _XfourDeep: ...


class _XfourIface: ...


@dataclasses.dataclass
class _XfourCaller:
    dep: _XfourIface


class _XfourGroup(Group):
    deep = providers.Factory(scope=Scope.REQUEST, creator=_XfourDeep)
    iface = providers.Alias(source_type=_XfourDeep, bound_type=_XfourIface)
    caller = providers.Factory(scope=Scope.APP, creator=_XfourCaller)


def test_validate_flags_shallow_caller_depending_through_alias_on_deeper_source() -> None:
    container = Container(scope=Scope.APP, groups=[_XfourGroup], validate=True)
    with pytest.raises(exceptions.ValidationFailedError) as exc_info:
        container.open()  # deferred validation runs at entry
    assert any(isinstance(e, exceptions.InvalidScopeDependencyError) for e in exc_info.value.errors)
    assert "REQUEST" in str(exc_info.value)


class _OkDeep: ...


class _OkIface: ...


@dataclasses.dataclass
class _OkCaller:
    dep: _OkIface


class _OkGroup(Group):
    deep = providers.Factory(scope=Scope.REQUEST, creator=_OkDeep)
    iface = providers.Alias(source_type=_OkDeep, bound_type=_OkIface)
    caller = providers.Factory(scope=Scope.REQUEST, creator=_OkCaller)


def test_validate_allows_same_scope_caller_through_alias() -> None:
    Container(scope=Scope.APP, groups=[_OkGroup], validate=True).open()  # deferred validation runs at entry


class _ChainTerminal: ...


class _MidIface: ...


class _TopIface: ...


@dataclasses.dataclass
class _ChainCaller:
    dep: _TopIface


class _AliasOfAliasGroup(Group):
    terminal = providers.Factory(scope=Scope.REQUEST, creator=_ChainTerminal)
    mid = providers.Alias(source_type=_ChainTerminal, bound_type=_MidIface)
    top = providers.Alias(source_type=_MidIface, bound_type=_TopIface)
    caller = providers.Factory(scope=Scope.APP, creator=_ChainCaller)


def test_validate_follows_alias_of_alias_to_terminal_scope() -> None:
    # caller(APP) -> top(alias) -> mid(alias) -> terminal(REQUEST): effective scope follows 2 hops -> flagged
    container = Container(scope=Scope.APP, groups=[_AliasOfAliasGroup], validate=True)
    with pytest.raises(exceptions.ValidationFailedError) as exc_info:
        container.open()  # deferred validation runs at entry
    assert any(isinstance(e, exceptions.InvalidScopeDependencyError) for e in exc_info.value.errors)
    assert "REQUEST" in str(exc_info.value)


class _MutualA: ...


class _MutualB: ...


class _MutualAliasGroup(Group):
    a = providers.Alias(source_type=_MutualB, bound_type=_MutualA)
    b = providers.Alias(source_type=_MutualA, bound_type=_MutualB)


def test_terminal_scope_handles_mutual_alias_cycle() -> None:
    # Mutual aliases: terminal_scope must terminate via the `seen` guard and fall back to `a`'s own scope.
    container = Container(scope=Scope.APP, groups=[_MutualAliasGroup], validate=False)
    assert DependencyGraph().terminal_scope(_MutualAliasGroup.a, container) is _MutualAliasGroup.a.scope
    # validate() also reports the cycle separately.
    with pytest.raises(exceptions.ValidationFailedError) as exc_info:
        container.validate()
    assert any(isinstance(e, exceptions.CircularDependencyError) for e in exc_info.value.errors)


class _DepSrc: ...


def test_alias_scope_param_removed() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument 'scope'"):
        providers.Alias(_DepSrc, scope=Scope.APP)  # ty: ignore[unknown-argument]


def test_alias_accepts_positional_source_type() -> None:
    class G(Group):
        repo = providers.Factory(creator=PostgresRepository, cache=True)
        abstract = providers.Alias(PostgresRepository, bound_type=AbstractRepository)

    container = Container(groups=[G], validate=True)
    container.open()
    assert isinstance(container.resolve(AbstractRepository), PostgresRepository)


def test_alias_rejects_source_type_passed_twice() -> None:
    with pytest.raises(TypeError, match="source_type"):
        providers.Alias(PostgresRepository, source_type=PostgresRepository)  # ty: ignore[parameter-already-assigned]


# redirect_target — node hook for transparent redirects


def test_redirect_target_default_none() -> None:
    class X: ...

    factory = providers.Factory(scope=Scope.APP, creator=X)
    assert factory.redirect_target(None) is None  # ty: ignore[invalid-argument-type]


def test_alias_redirect_target_returns_source() -> None:
    container = Container(groups=[MyGroup])
    source = container.providers_registry.find_provider(PostgresRepository)
    assert source is not None
    target = MyGroup.abstract_repo.redirect_target(container)
    assert target is not None
    assert target.provider_id == source.provider_id


def test_alias_redirect_target_none_when_dangling() -> None:
    class G(Group):
        abstract = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)

    container = Container(groups=[G])
    assert G.abstract.redirect_target(container) is None
