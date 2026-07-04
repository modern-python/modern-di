import dataclasses
import warnings

import pytest

from modern_di import Container, Group, Scope, exceptions, providers
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
    concrete = container.resolve(PostgresRepository)
    abstract = container.resolve(AbstractRepository)
    assert isinstance(abstract, PostgresRepository)
    assert concrete is abstract


def test_alias_without_caching_returns_fresh_instance_per_call() -> None:
    class G(Group):
        repo = providers.Factory(creator=PostgresRepository)
        abstract = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)

    container = Container(groups=[G])
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
    with pytest.raises(ScopeNotInitializedError):
        app_container.resolve(AbstractRepository)

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance = request_container.resolve(AbstractRepository)
    assert isinstance(instance, PostgresRepository)


def test_alias_override_does_not_affect_source() -> None:
    container = Container(groups=[MyGroup])
    mock = PostgresRepository(dsn="mock-alias")
    container.override(MyGroup.abstract_repo, mock)

    assert container.resolve(AbstractRepository) is mock
    assert container.resolve(PostgresRepository) is not mock


def test_source_override_propagates_through_alias() -> None:
    container = Container(groups=[MyGroup])
    mock = PostgresRepository(dsn="mock-source")
    container.override(MyGroup.repo, mock)

    assert container.resolve(PostgresRepository) is mock
    assert container.resolve(AbstractRepository) is mock


def test_alias_missing_source_raises_on_resolve() -> None:
    class G(Group):
        abstract = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)

    container = Container(groups=[G])
    with pytest.raises(AliasSourceNotRegisteredError, match="PostgresRepository") as exc:
        container.resolve(AbstractRepository)
    assert exc.value.source_type is PostgresRepository


def test_alias_missing_source_raises_on_validate_provider() -> None:
    class G(Group):
        abstract = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)

    container = Container(groups=[G])
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

    with pytest.raises(ValidationFailedError) as exc:
        Container(groups=[G], validate=True)
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)
    assert "Concrete" in str(issue)


def test_alias_default_bound_type_is_source_type() -> None:
    alias = providers.Alias(source_type=PostgresRepository)
    assert alias.bound_type is PostgresRepository


def test_alias_repr() -> None:
    with pytest.warns(DeprecationWarning, match="scope"):
        alias = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository, scope=Scope.REQUEST)
    assert repr(alias) == (
        f"Alias(source_type={PostgresRepository!r}, bound_type={AbstractRepository!r}, scope=<Scope.REQUEST: 3>)"
    )


class _NotRegisteredSource: ...


class _AliasTarget: ...


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class _NeedsUnregistered:
    dep: _NotRegisteredSource


class _DanglingAliasGroup(Group):
    dangling = providers.Alias(source_type=_NotRegisteredSource, bound_type=_AliasTarget)
    broken_factory = providers.Factory(creator=_NeedsUnregistered)


def test_validate_aggregates_dangling_alias_into_validation_failed_error() -> None:
    with pytest.raises(ValidationFailedError) as exc_info:
        Container(scope=Scope.APP, groups=[_DanglingAliasGroup], validate=True)
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
    impl = container.resolve(_ChainImpl)
    assert container.resolve(_ChainIfB) is impl
    assert container.resolve(_ChainIfA) is impl


def test_alias_resolved_from_child_returns_app_cached_singleton() -> None:
    container = Container(scope=Scope.APP, groups=[_ChainGroup])
    app_instance = container.resolve(_ChainImpl)
    request = container.build_child_container(scope=Scope.REQUEST)
    assert request.resolve(_ChainIfA) is app_instance


# X-4 — Alias.scope is decorative; validate() must not flag alias->source on scope ordering


class _DeepImpl: ...


class _ShallowIface: ...


class _AliasScopeGroup(Group):
    impl = providers.Factory(scope=Scope.REQUEST, creator=_DeepImpl)
    iface = providers.Alias(source_type=_DeepImpl, bound_type=_ShallowIface)  # default APP scope, shallower than source


def test_validate_does_not_flag_alias_whose_scope_is_shallower_than_source() -> None:
    app = Container(scope=Scope.APP, groups=[_AliasScopeGroup])
    app.validate()  # must NOT raise for the alias->impl edge
    request = app.build_child_container(scope=Scope.REQUEST)
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
    container = Container(scope=Scope.APP, groups=[_AliasChainErrGroup])
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
    container = Container(scope=Scope.APP, groups=[_NullBoundAliasGroup])
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
    with pytest.raises(exceptions.ValidationFailedError) as exc_info:
        Container(scope=Scope.APP, groups=[_XfourGroup], validate=True)
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
    Container(scope=Scope.APP, groups=[_OkGroup], validate=True)  # must not raise


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
    with pytest.raises(exceptions.ValidationFailedError) as exc_info:
        Container(scope=Scope.APP, groups=[_AliasOfAliasGroup], validate=True)
    assert any(isinstance(e, exceptions.InvalidScopeDependencyError) for e in exc_info.value.errors)
    assert "REQUEST" in str(exc_info.value)


class _MutualA: ...


class _MutualB: ...


class _MutualAliasGroup(Group):
    a = providers.Alias(source_type=_MutualB, bound_type=_MutualA)
    b = providers.Alias(source_type=_MutualA, bound_type=_MutualB)


def test_effective_scope_handles_mutual_alias_cycle() -> None:
    # Mutual aliases: effective_scope must terminate via the `seen` guard and fall back to self.scope.
    container = Container(scope=Scope.APP, groups=[_MutualAliasGroup])
    assert _MutualAliasGroup.a.effective_scope(container) is _MutualAliasGroup.a.scope
    # validate() also reports the cycle separately.
    with pytest.raises(exceptions.ValidationFailedError) as exc_info:
        container.validate()
    assert any(isinstance(e, exceptions.CircularDependencyError) for e in exc_info.value.errors)


class _DepSrc: ...


def test_alias_scope_parameter_is_deprecated() -> None:
    with pytest.warns(DeprecationWarning, match="scope"):
        providers.Alias(source_type=_DepSrc, bound_type=object, scope=Scope.REQUEST)


def test_alias_without_scope_emits_no_deprecation_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        alias = providers.Alias(source_type=_DepSrc, bound_type=object)
    assert alias is not None
