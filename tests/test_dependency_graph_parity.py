import pytest

from modern_di import Container, Scope, dependency_graph, exceptions
from modern_di.group import Group
from modern_di.providers import Factory


class _A:
    def __init__(self, b: "_B") -> None: ...


class _B:
    def __init__(self, a: _A) -> None: ...


def test_cycle_path_and_locations_shape() -> None:
    class G(Group):
        a = Factory(scope=Scope.APP, creator=_A)
        b = Factory(scope=Scope.APP, creator=_B)

    container = Container(scope=Scope.APP, groups=[G], validate=False)
    with pytest.raises(exceptions.ValidationFailedError) as ei:
        container.validate()
    cyc = next(e for e in ei.value.errors if isinstance(e, exceptions.CircularDependencyError))
    # loop closes by repeating the first node
    assert cyc.cycle_path[0] == cyc.cycle_path[-1]
    assert cyc.cycle_locations is not None
    assert len(cyc.cycle_locations) == len(cyc.cycle_path)


def test_validate_collects_all_error_kinds_once() -> None:
    # a graph with a scope inversion AND a missing dep surfaces both, in one call
    class Dep: ...

    class Needs:
        def __init__(self, dep: Dep) -> None: ...

    class Deep: ...

    class Shallow:  # APP-scoped, depends on REQUEST-scoped Deep -> scope inversion
        def __init__(self, deep: Deep) -> None: ...

    class G(Group):
        needs = Factory(scope=Scope.APP, creator=Needs)  # dep unregistered -> ArgumentResolutionError
        deep = Factory(scope=Scope.REQUEST, creator=Deep)
        shallow = Factory(scope=Scope.APP, creator=Shallow)  # deeper dep -> InvalidScopeDependencyError

    container = Container(scope=Scope.APP, groups=[G], validate=False)
    with pytest.raises(exceptions.ValidationFailedError) as ei:
        container.validate()
    assert any(isinstance(e, exceptions.ArgumentResolutionError) for e in ei.value.errors)
    assert any(isinstance(e, exceptions.InvalidScopeDependencyError) for e in ei.value.errors)


def test_validate_is_free_when_already_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    class X: ...

    class G(Group):
        x = Factory(scope=Scope.APP, creator=X)

    container = Container(scope=Scope.APP, groups=[G], validate=True)

    def _explode(*_: object, **__: object) -> object:  # pragma: no cover
        msg = "re-walked"
        raise AssertionError(msg)

    monkeypatch.setattr(dependency_graph.DependencyGraph, "walk", _explode)
    container.validate()  # short-circuited on validated_version == version -> no walk


def test_runtime_guard_converts_unvalidated_cycle() -> None:
    class G(Group):
        a = Factory(scope=Scope.APP, creator=_A)
        b = Factory(scope=Scope.APP, creator=_B)

    container = Container(scope=Scope.APP, groups=[G], validate=False)
    with pytest.raises(exceptions.CircularDependencyError):
        container.resolve(_A)
