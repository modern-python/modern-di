import dataclasses
import inspect
import operator

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import (
    CircularDependencyError,
    InvalidScopeDependencyError,
    ScopeNotInitializedError,
    ValidationFailedError,
)


@dataclasses.dataclass(kw_only=True, slots=True)
class Settings:
    db_dsn: str = "postgresql://localhost/app"
    db_pool_size: int = 5
    urls: dict[str, str] = dataclasses.field(default_factory=lambda: {"db": "postgresql://ro/app"})


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Database:
    dsn: str
    pool_size: int


class Dependencies(Group):
    settings = providers.Factory(Settings, cache=True)
    database = providers.Factory(
        Database,
        kwargs={
            "dsn": settings.derive(lambda s: s.db_dsn),
            "pool_size": settings.derive(lambda s: s.db_pool_size),
        },
    )


def test_derived_value_is_fn_of_the_source() -> None:
    container = Container(groups=[Dependencies])
    container.validate()
    assert container.resolve(Database) == Database(dsn="postgresql://localhost/app", pool_size=5)


def test_validate_never_calls_fn() -> None:
    calls: list[Settings] = []

    class G(Group):
        settings = providers.Factory(Settings)
        dsn = settings.derive(calls.append)

    Container(groups=[G]).validate()
    assert calls == []


def test_derived_provider_resolves_by_reference() -> None:
    url = Dependencies.settings.derive(lambda s: s.urls["db"])
    assert Container(groups=[Dependencies]).resolve_provider(url) == "postgresql://ro/app"


def test_source_override_reaches_a_derived_value_resolved_before() -> None:
    container = Container(groups=[Dependencies])
    assert container.resolve(Database).dsn == "postgresql://localhost/app"

    container.override(Dependencies.settings, Settings(db_dsn="postgresql://test/app"))
    assert container.resolve(Database).dsn == "postgresql://test/app"

    container.reset_override(Dependencies.settings)
    assert container.resolve(Database).dsn == "postgresql://localhost/app"


def test_derived_provider_can_be_overridden_itself() -> None:
    dsn = Dependencies.settings.derive(lambda s: s.db_dsn)
    container = Container(groups=[Dependencies])
    container.override(dsn, "sqlite://")
    assert container.resolve_provider(dsn) == "sqlite://"
    assert container.resolve(Settings).db_dsn == "postgresql://localhost/app"


def test_derived_value_is_never_cached() -> None:
    calls: list[Settings] = []

    def pick(settings: Settings) -> str:
        calls.append(settings)
        return settings.db_dsn

    class G(Group):
        settings = providers.Factory(Settings)
        dsn = settings.derive(pick)

    container = Container(groups=[G])
    container.resolve_provider(G.dsn)
    container.resolve_provider(G.dsn)
    first, second = calls
    assert first is not second


def test_derive_chains() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Nested:
        db: Settings = dataclasses.field(default_factory=Settings)

    nested = providers.Factory(Nested, bound_type=None)
    container = Container()
    assert container.resolve_provider(nested.derive(lambda n: n.db).derive(lambda s: s.db_dsn)) == (
        "postgresql://localhost/app"
    )


def test_derived_provider_in_a_request_group_takes_its_sources_scope() -> None:
    class G(Group, scope=Scope.REQUEST):
        settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
        dsn = settings.derive(lambda s: s.db_dsn)

    container = Container(groups=[G])
    container.validate()
    assert container.resolve_provider(G.dsn) == "postgresql://localhost/app"


def test_inline_derived_provider_over_a_request_source_validates_and_resolves() -> None:
    class G(Group, scope=Scope.REQUEST):
        settings = providers.Factory(Settings, cache=True)
        database = providers.Factory(
            Database,
            kwargs={"dsn": settings.derive(lambda s: s.db_dsn), "pool_size": 1},
        )

    container = Container(groups=[G])
    container.validate()
    with container.build_child_container(scope=Scope.REQUEST) as request_container:
        assert request_container.resolve(Database).dsn == "postgresql://localhost/app"


def test_validate_rejects_an_app_factory_reading_a_request_source_through_derive() -> None:
    class G(Group):
        settings = providers.Factory(Settings, scope=Scope.REQUEST)
        database = providers.Factory(
            Database,
            kwargs={"dsn": settings.derive(lambda s: s.db_dsn), "pool_size": 1},
        )

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.exceptions
    assert isinstance(issue, InvalidScopeDependencyError)
    assert issue.parameter_name == "dsn"
    assert issue.dependency_terminal is G.settings


def test_source_scope_error_names_the_derived_step() -> None:
    class G(Group):
        settings = providers.Factory(Settings, scope=Scope.REQUEST)
        dsn = settings.derive(lambda s: s.db_dsn)

    with pytest.raises(ScopeNotInitializedError) as exc:
        Container(groups=[G]).resolve_provider(G.dsn)
    assert [(step.scope, step.name) for step in exc.value.dependency_path] == [
        (Scope.REQUEST, "Settings.derive"),
        (Scope.REQUEST, "Settings"),
    ]


def test_fn_error_is_reraised_unchanged_with_a_note_naming_the_derived_provider() -> None:
    def broken(settings: Settings) -> str:
        return settings.missing  # ty: ignore[unresolved-attribute]

    class G(Group):
        settings = providers.Factory(Settings)
        dsn = settings.derive(broken)

    with pytest.raises(AttributeError, match="missing") as exc:
        Container(groups=[G]).resolve_provider(G.dsn)
    line = broken.__code__.co_firstlineno
    assert exc.value.__notes__ == [f"raised by the function of Settings.derive ({__name__}:{line})"]


def test_derived_provider_without_source_code_is_located_at_the_derive_call() -> None:
    getter = operator.attrgetter("db_dsn")
    frame = inspect.currentframe()
    assert frame is not None
    dsn = Dependencies.settings.derive(getter)
    assert dsn.definition_site == f"{__name__}:{frame.f_lineno - 1}"
    assert repr(dsn) == f"Settings.derive({getter!r})"
    assert Container(groups=[Dependencies]).resolve_provider(dsn) == "postgresql://localhost/app"


def test_derived_provider_over_the_container() -> None:
    scope = providers.container_provider.derive(lambda c: c.scope)
    container = Container(groups=[Dependencies])
    container.validate()
    assert container.resolve_provider(scope) is Scope.APP


def test_cycle_through_a_derived_provider_is_reported() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
    class Inner:
        name: str

    @dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
    class Outer:
        inner: Inner

    class G(Group):
        outer = providers.Factory(Outer)
        inner = providers.Factory(Inner, kwargs={"name": outer.derive(lambda o: o.inner.name)})

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.exceptions
    assert isinstance(issue, CircularDependencyError)
    assert [step.name for step in issue.steps] == ["Outer", "Inner", "Outer.derive", "Outer"]
