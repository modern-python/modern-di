import dataclasses
import inspect

import pytest

from modern_di import Container, Group, Scope, exceptions, providers
from modern_di.exceptions import (
    ArgumentResolutionError,
    ContainerError,
    ProviderNotRegisteredError,
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
    container.open()
    with pytest.raises(ArgumentResolutionError) as exc_info:
        container.resolve(MyService)

    exc = exc_info.value
    # The structured path is the stable contract; the rendered string is checked via substrings
    # rather than exact whitespace so cosmetic formatting can evolve without churning this test.
    # `location` is asserted separately (test_breadcrumb_line_carries_definition_site); ignored
    # here so this test doesn't hardcode fixture line numbers.
    assert [(step.scope, step.name) for step in exc.dependency_path] == [
        (Scope.APP, "MyService"),
        (Scope.APP, "Repository"),
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
    container.open()
    request = container.build_child_container(scope=Scope.REQUEST)
    request.open()
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
    app_container.open()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.open()

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
    app_container.open()
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


def test_breadcrumb_line_carries_definition_site() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
    class _Anchored:
        pass

    class _G(Group):
        anchored = providers.Factory(_Anchored, scope=Scope.REQUEST)

    container = Container(groups=[_G])
    container.open()
    with pytest.raises(ScopeNotInitializedError) as exc_info:
        container.resolve(_Anchored)
    lineno = inspect.getsourcelines(_Anchored)[1]
    assert f"({_Anchored.__module__}:{lineno})" in str(exc_info.value)


class _Deep:
    pass


class _MidIface:
    pass


class _TopIface:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class _Captor:
    svc: _TopIface


class _AliasScopeViolationGroup(Group):
    deep = providers.Factory(scope=Scope.REQUEST, creator=_Deep)
    mid = providers.Alias(source_type=_Deep, bound_type=_MidIface)
    top = providers.Alias(source_type=_MidIface, bound_type=_TopIface)
    captor = providers.Factory(scope=Scope.APP, creator=_Captor)


def _validate_chain_names() -> list[str]:
    container = Container(groups=[_AliasScopeViolationGroup])
    with pytest.raises(exceptions.ValidationFailedError) as exc_info:
        container.validate()
    (issue,) = [e for e in exc_info.value.errors if isinstance(e, exceptions.InvalidScopeDependencyError)]
    return [issue.provider.display_name, *(p.display_name for p in issue.dep_chain)]


def _runtime_chain_names() -> list[str]:
    container = Container(groups=[_AliasScopeViolationGroup])
    container.open()
    with pytest.raises(ScopeNotInitializedError) as exc_info:
        container.resolve(_Captor)
    return [step.name for step in exc_info.value.dependency_path]


def test_validate_and_runtime_name_the_same_chain_for_one_scope_violation() -> None:
    """INVARIANT: both detectors of a scope violation name the same provider chain.

    Broken by any error that reports a redirect-mediated violation from only one end of the
    chain: naming the bound type without its terminal, or the terminal without the hops that
    reached it. The two paths share `_render_chain` precisely so a reader who hits one and
    then the other is not told two different stories about the same graph.
    """
    assert _validate_chain_names() == _runtime_chain_names()
