import dataclasses
import typing

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import ArgumentResolutionError, ProviderNotRegisteredError
from modern_di.registries.providers_registry import _hierarchy_hint


class Database:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class PostgresDatabase(Database):
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class Repository:
    pass


def test_subclass_suggestion() -> None:
    class G(Group):
        db = providers.Factory(creator=PostgresDatabase)

    container = Container(groups=[G])
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        container.resolve(Database)

    assert str(exc_info.value) == (
        "Provider of type <class 'tests.test_suggestions.Database'> is not registered in providers registry.\n"
        "Did you mean:\n"
        "  - PostgresDatabase (registered subclass, scope=APP)"
    )


def test_baseclass_suggestion() -> None:
    class G(Group):
        db = providers.Factory(creator=Database)

    container = Container(groups=[G])
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        container.resolve(PostgresDatabase)

    assert str(exc_info.value) == (
        "Provider of type <class 'tests.test_suggestions.PostgresDatabase'> is not registered in providers registry.\n"
        "Did you mean:\n"
        "  - Database (registered base class, scope=APP)"
    )


def test_typo_suggestion() -> None:
    class G(Group):
        repo = providers.Factory(creator=Repository)

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Repostory:
        pass

    container = Container(groups=[G])
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        container.resolve(Repostory)

    assert str(exc_info.value) == (
        "Provider of type "
        "<class 'tests.test_suggestions.test_typo_suggestion.<locals>.Repostory'> "
        "is not registered in providers registry.\n"
        "Did you mean:\n"
        "  - Repository (similar name, scope=APP)"
    )


def test_suggestion_includes_provider_scope() -> None:
    class G(Group):
        db = providers.Factory(scope=Scope.REQUEST, creator=PostgresDatabase)

    container = Container(groups=[G])
    request_container = container.build_child_container(scope=Scope.REQUEST)
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        request_container.resolve(Database)

    assert str(exc_info.value) == (
        "Provider of type <class 'tests.test_suggestions.Database'> is not registered in providers registry.\n"
        "Did you mean:\n"
        "  - PostgresDatabase (registered subclass, scope=REQUEST)"
    )


def test_no_suggestions_when_nothing_matches() -> None:
    container = Container()
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        container.resolve(int)

    assert str(exc_info.value) == "Provider of type <class 'int'> is not registered in providers registry."


def test_suggestions_capped_at_three() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class A1(Database):
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class A2(Database):
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class A3(Database):
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class A4(Database):
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class A5(Database):
        pass

    class G(Group):
        a1 = providers.Factory(creator=A1)
        a2 = providers.Factory(creator=A2)
        a3 = providers.Factory(creator=A3)
        a4 = providers.Factory(creator=A4)
        a5 = providers.Factory(creator=A5)

    container = Container(groups=[G])
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        container.resolve(Database)

    assert str(exc_info.value) == (
        "Provider of type <class 'tests.test_suggestions.Database'> is not registered in providers registry.\n"
        "Did you mean:\n"
        "  - A1 (registered subclass, scope=APP)\n"
        "  - A2 (registered subclass, scope=APP)\n"
        "  - A3 (registered subclass, scope=APP)"
    )


def test_hierarchy_hint_skips_non_class_bound_type() -> None:
    provider = providers.Factory(creator=list, bound_type=list[int])
    assert _hierarchy_hint(int, provider) is None


def test_hierarchy_hint_swallows_protocol_typeerror() -> None:
    class MyProto(typing.Protocol):
        def foo(self) -> None: ...

    provider = providers.Factory(creator=lambda: 1, bound_type=int)
    assert _hierarchy_hint(MyProto, provider) is None


def test_argument_resolution_subclass_suggestion() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        db: Database

    class G(Group):
        db = providers.Factory(creator=PostgresDatabase)
        service = providers.Factory(creator=Service)

    container = Container(groups=[G])
    with pytest.raises(ArgumentResolutionError) as exc_info:
        container.resolve(Service)

    rendered = str(exc_info.value)
    assert "Did you mean:" in rendered
    assert "PostgresDatabase (registered subclass, scope=APP)" in rendered
    assert exc_info.value.suggestions == ["  - PostgresDatabase (registered subclass, scope=APP)"]


def test_argument_resolution_baseclass_suggestion() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        db: PostgresDatabase

    class G(Group):
        db = providers.Factory(creator=Database)
        service = providers.Factory(creator=Service)

    container = Container(groups=[G])
    with pytest.raises(ArgumentResolutionError) as exc_info:
        container.resolve(Service)

    rendered = str(exc_info.value)
    assert "Did you mean:" in rendered
    assert "Database (registered base class, scope=APP)" in rendered


def test_argument_resolution_typo_suggestion() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Repostory:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        repo: Repostory

    class G(Group):
        repo = providers.Factory(creator=Repository)
        service = providers.Factory(creator=Service)

    container = Container(groups=[G])
    with pytest.raises(ArgumentResolutionError) as exc_info:
        container.resolve(Service)

    rendered = str(exc_info.value)
    assert "Did you mean:" in rendered
    assert "Repository (similar name, scope=APP)" in rendered


def test_argument_resolution_no_suggestions_when_nothing_matches() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        n: int

    class G(Group):
        service = providers.Factory(creator=Service)

    container = Container(groups=[G])
    with pytest.raises(ArgumentResolutionError) as exc_info:
        container.resolve(Service)

    assert "Did you mean:" not in str(exc_info.value)
    assert exc_info.value.suggestions == []


def test_hierarchy_hint_preferred_over_typo() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Databse:
        pass

    class G(Group):
        db = providers.Factory(creator=PostgresDatabase)
        typo = providers.Factory(creator=Databse)

    container = Container(groups=[G])
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        container.resolve(Database)

    assert str(exc_info.value) == (
        "Provider of type <class 'tests.test_suggestions.Database'> is not registered in providers registry.\n"
        "Did you mean:\n"
        "  - PostgresDatabase (registered subclass, scope=APP)\n"
        "  - Databse (similar name, scope=APP)"
    )
