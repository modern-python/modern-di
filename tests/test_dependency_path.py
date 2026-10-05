import dataclasses
import inspect

import pytest

from modern_di import Container, Group, Scope, exceptions, providers
from modern_di.exceptions import (
    ArgumentResolutionError,
    ContainerClosedError,
    ContainerError,
    ProviderNotRegisteredError,
    ResolutionError,
    ScopeNotInitializedError,
    ScopeSkippedError,
)
from modern_di.exceptions.base import DependencyPathMixin


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


def test_resolution_error_catches_scope_not_initialized() -> None:
    class _G(Group):
        resource = providers.Factory(scope=Scope.REQUEST, creator=ScopedResource)

    container = Container(groups=[_G])
    with pytest.raises(ResolutionError) as exc_info:
        container.resolve(ScopedResource)
    assert isinstance(exc_info.value, ScopeNotInitializedError)
    assert isinstance(exc_info.value, ContainerError)


def test_resolution_error_catches_scope_skipped() -> None:
    class _G(Group):
        resource = providers.Factory(scope=Scope.APP, creator=ScopedResource)

    container = Container(scope=Scope.REQUEST, groups=[_G])
    with pytest.raises(ResolutionError) as exc_info:
        container.resolve(ScopedResource)
    assert isinstance(exc_info.value, ScopeSkippedError)
    assert isinstance(exc_info.value, ContainerError)


def test_resolution_error_catches_container_closed() -> None:
    class _G(Group):
        resource = providers.Factory(creator=ScopedResource)

    container = Container(groups=[_G])
    container.close_sync()
    with pytest.raises(ResolutionError) as exc_info:
        container.resolve(ScopedResource)
    assert isinstance(exc_info.value, ContainerClosedError)
    assert isinstance(exc_info.value, ContainerError)


def test_closed_ancestor_reached_through_a_dependency_renders_without_chain() -> None:
    class _G(Group):
        resource = providers.Factory(scope=Scope.APP, creator=ScopedResource)
        consumer = providers.Factory(scope=Scope.REQUEST, creator=CaptiveConsumer)

    app = Container(groups=[_G])
    request = app.build_child_container(scope=Scope.REQUEST)
    app.close_sync()
    with pytest.raises(ContainerClosedError) as exc_info:
        request.resolve(CaptiveConsumer)
    assert exc_info.value.dependency_path == []
    assert str(exc_info.value) == (
        "Container (scope APP) is closed. Reopen it with `open()` or by re-entering `with`/`async with` "
        "before resolving from it or from any of its child containers.\n"
        "See: https://modern-di.modern-python.org/troubleshooting/container-closed-error/"
    )


def test_dependency_path_mixin_is_not_an_exception() -> None:
    # Guards the ruling: DependencyPathMixin must never become except-catchable on its own.
    assert not issubclass(DependencyPathMixin, BaseException)


def test_breadcrumb_line_carries_definition_site() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
    class _Anchored:
        pass

    class _G(Group):
        anchored = providers.Factory(_Anchored, scope=Scope.REQUEST)

    container = Container(groups=[_G])
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
    with pytest.raises(ScopeNotInitializedError) as exc_info:
        container.resolve(_Captor)
    return [step.name for step in exc_info.value.dependency_path]


def test_validate_and_runtime_name_the_same_chain_for_one_scope_violation() -> None:
    """INVARIANT: both detectors of a scope violation name the same provider chain.

    Broken by any error that reports a redirect-mediated violation from only one end of the
    chain: naming the bound type without its terminal, or the terminal without the hops that
    reached it. The two paths share `render_chain` precisely so a reader who hits one and
    then the other is not told two different stories about the same graph.
    """
    assert _validate_chain_names() == _runtime_chain_names()


class _EdgeIface:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class _AliasFirst:
    via_alias: _EdgeIface
    direct: ScopedResource


@dataclasses.dataclass(kw_only=True, slots=True)
class _DirectFirst:
    direct: ScopedResource
    via_alias: _EdgeIface


class _TwoEdgesGroup(Group):
    resource = providers.Factory(scope=Scope.REQUEST, creator=ScopedResource)
    iface = providers.Alias(source_type=ScopedResource, bound_type=_EdgeIface)
    alias_first = providers.Factory(scope=Scope.APP, creator=_AliasFirst)
    direct_first = providers.Factory(scope=Scope.APP, creator=_DirectFirst)


@pytest.mark.parametrize(
    ("consumer", "expected"),
    [
        (_AliasFirst, ["_AliasFirst", "_EdgeIface", "ScopedResource"]),
        (_DirectFirst, ["_DirectFirst", "ScopedResource"]),
    ],
)
def test_runtime_chain_names_the_edge_that_failed(consumer: type, expected: list[str]) -> None:
    container = Container(groups=[_TwoEdgesGroup])
    with pytest.raises(ScopeNotInitializedError) as exc_info:
        container.resolve(consumer)
    assert [step.name for step in exc_info.value.dependency_path] == expected


class _DanglingIface:
    pass


class _DanglingSource:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class _NeedsDangling:
    dep: _DanglingIface


class _DanglingUnderParentGroup(Group):
    iface = providers.Alias(source_type=_DanglingSource, bound_type=_DanglingIface)
    parent = providers.Factory(creator=_NeedsDangling)


def test_dangling_alias_under_a_parent_names_both() -> None:
    container = Container(groups=[_DanglingUnderParentGroup])
    with pytest.raises(exceptions.AliasSourceNotRegisteredError) as exc_info:
        container.resolve(_NeedsDangling)
    assert [step.name for step in exc_info.value.dependency_path] == ["_NeedsDangling", "_DanglingIface"]
