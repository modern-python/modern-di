import dataclasses

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import ArgumentResolutionError, ProviderNotRegisteredError, ResolutionStep


@dataclasses.dataclass(kw_only=True, slots=True)
class Database:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class Repository:
    db: Database


@dataclasses.dataclass(kw_only=True, slots=True)
class MyService:
    repo: Repository


class IncompleteGroup(Group):
    repo = providers.Factory(creator=Repository)
    svc = providers.Factory(creator=MyService)


def test_chain_appears_when_arg_unresolvable() -> None:
    container = Container(groups=[IncompleteGroup])
    with pytest.raises(ArgumentResolutionError) as exc_info:
        container.resolve(MyService)

    exc = exc_info.value
    # The structured path is the stable contract; the rendered string is checked via substrings
    # rather than exact whitespace so cosmetic formatting can evolve without churning this test.
    assert exc.dependency_path == [
        ResolutionStep(scope=Scope.APP, name="MyService"),
        ResolutionStep(scope=Scope.APP, name="Repository"),
    ]
    rendered = str(exc)
    assert rendered.startswith("Cannot resolve dependency chain:")
    assert "MyService" in rendered
    assert "└─> Repository" in rendered
    assert "caused by: Argument db" in rendered


def test_no_chain_when_top_level_provider_missing() -> None:
    container = Container()
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        container.resolve(str)
    assert exc_info.value.dependency_path == []
    assert "Cannot resolve dependency chain" not in str(exc_info.value)


def test_chain_includes_scope_name() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Outer:
        inner: Repository

    class CrossScope(Group):
        repo = providers.Factory(scope=Scope.REQUEST, creator=Repository)
        outer = providers.Factory(scope=Scope.REQUEST, creator=Outer)

    container = Container(groups=[CrossScope])
    request = container.build_child_container(scope=Scope.REQUEST)
    with pytest.raises(ArgumentResolutionError) as exc_info:
        request.resolve(Outer)

    rendered = str(exc_info.value)
    assert "REQUEST" in rendered
    assert exc_info.value.dependency_path[0].scope == Scope.REQUEST
