import dataclasses

import pytest

from modern_di import Container, Group, Scope, providers
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
    repo = providers.Factory(creator=PostgresRepository, cache_settings=providers.CacheSettings())
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


def test_alias_missing_source_raises_on_container_validate() -> None:
    class G(Group):
        abstract = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository)

    with pytest.raises(AliasSourceNotRegisteredError, match="PostgresRepository"):
        Container(groups=[G], validate=True)


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
    alias = providers.Alias(source_type=PostgresRepository, bound_type=AbstractRepository, scope=Scope.REQUEST)
    assert repr(alias) == (
        f"Alias(source_type={PostgresRepository!r}, bound_type={AbstractRepository!r}, scope=<Scope.REQUEST: 3>)"
    )
