import dataclasses

import pytest

from modern_di import Container, Group, Scope, exceptions, providers
from modern_di.exceptions import (
    ArgumentResolutionError,
    ContainerError,
    ProviderNotRegisteredError,
    ResolutionStep,
    ScopeNotInitializedError,
)


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
    # The trailer is always the final line, even when the message is the path-block rendering.
    assert rendered.endswith("See: https://modern-di.modern-python.org/troubleshooting/argument-resolution-error/")


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


@dataclasses.dataclass(kw_only=True, slots=True)
class ScopedResource:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class CaptiveConsumer:
    resource: ScopedResource


class AbstractResource: ...


def test_scope_error_at_direct_container_call_has_empty_path() -> None:
    # No provider frame is ever entered (find_container is called directly, not via
    # resolve()), so the dependency_path stays empty and the message is exactly today's.
    container = Container()
    with pytest.raises(ScopeNotInitializedError) as exc_info:
        container.find_container(Scope.REQUEST)

    exc = exc_info.value
    assert exc.dependency_path == []
    assert str(exc) == (
        "Provider of scope REQUEST cannot be resolved in container of scope APP.\n"
        "See: https://modern-di.modern-python.org/troubleshooting/scope-not-initialized-error/"
    )


def test_captive_dependency_names_both_ends() -> None:
    # The report's live-verified scenario: an APP-scoped factory captively depends on a
    # REQUEST-scoped provider. Resolving it from a REQUEST container still fails (the
    # captured object would outlive its scope), but the message must now name both the
    # captor and the captive, not just the two scope names.
    class CaptiveGroup(Group):
        resource = providers.Factory(scope=Scope.REQUEST, creator=ScopedResource)
        consumer = providers.Factory(scope=Scope.APP, creator=CaptiveConsumer)

    app_container = Container(groups=[CaptiveGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)

    with pytest.raises(ScopeNotInitializedError) as exc_info:
        request_container.resolve(CaptiveConsumer)

    exc = exc_info.value
    assert [step.name for step in exc.dependency_path] == ["CaptiveConsumer", "ScopedResource"]
    rendered = str(exc)
    assert rendered.startswith("Cannot resolve dependency chain:")
    assert "CaptiveConsumer" in rendered
    assert "└─> ScopedResource" in rendered
    assert "caused by: Provider of scope REQUEST cannot be resolved in container of scope APP." in rendered


def test_alias_prepends_step_on_scope_error() -> None:
    class AliasCaptiveGroup(Group):
        resource = providers.Factory(scope=Scope.REQUEST, creator=ScopedResource)
        alias = providers.Alias(source_type=ScopedResource, bound_type=AbstractResource)

    app_container = Container(groups=[AliasCaptiveGroup])
    with pytest.raises(ScopeNotInitializedError) as exc_info:
        app_container.resolve(AbstractResource)

    exc = exc_info.value
    assert [step.name for step in exc.dependency_path] == ["AbstractResource", "ScopedResource"]
    rendered = str(exc)
    assert "caused by: Provider of scope REQUEST cannot be resolved in container of scope APP." in rendered


def test_scope_error_still_caught_as_container_error() -> None:
    container = Container()
    with pytest.raises(ContainerError) as exc_info:
        container.find_container(Scope.REQUEST)
    assert isinstance(exc_info.value, ScopeNotInitializedError)


def test_dependency_path_mixin_is_not_an_exception() -> None:
    # Guards the ruling: DependencyPathMixin must never become except-catchable on its own.
    assert not issubclass(exceptions.DependencyPathMixin, BaseException)
