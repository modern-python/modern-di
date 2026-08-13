"""Contract tests for the single graph traversal: cycle shape, error kinds, and the walk short-circuits.

(Formerly `test_dependency_graph_parity.py`, from when validate() and the runtime guard each
had their own walk to keep in sync. PR #308 unified them; there is no second implementation
to be at parity with.)
"""

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

    container = Container(scope=Scope.APP, groups=[G])
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

    container = Container(scope=Scope.APP, groups=[G])
    with pytest.raises(exceptions.ValidationFailedError) as ei:
        container.validate()
    assert any(isinstance(e, exceptions.ArgumentResolutionError) for e in ei.value.errors)
    assert any(isinstance(e, exceptions.InvalidScopeDependencyError) for e in ei.value.errors)


def test_validate_is_free_when_already_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    """INVARIANT: `_validated` memoizes a clean walk, so a repeat `validate()` skips the walk.

    A mutator that forgets to clear the flag leaves a stale clean result: `validate()` returns free
    without re-walking a graph that actually changed. That nothing validates automatically --
    construction, `add_providers`, `open()` and `resolve()` all leave the flag alone -- is proven
    separately by `test_construction_never_validates`,
    `test_add_providers_never_validates_and_does_not_roll_back`, `test_open_never_validates` and
    `test_resolve_never_validates` in `tests/test_container.py`.
    """

    class X: ...

    class G(Group):
        x = Factory(scope=Scope.APP, creator=X)

    container = Container(scope=Scope.APP, groups=[G])
    container.validate()  # this call does the walk (clean graph) and sets the registry's validated flag

    def _explode(*_: object, **__: object) -> object:  # pragma: no cover
        msg = "re-walked"
        raise AssertionError(msg)

    monkeypatch.setattr(dependency_graph.DependencyGraph, "walk", _explode)
    container.validate()  # short-circuited on the registry's validated flag -> no walk


def test_runtime_guard_converts_unvalidated_cycle() -> None:
    class G(Group):
        a = Factory(scope=Scope.APP, creator=_A)
        b = Factory(scope=Scope.APP, creator=_B)

    container = Container(scope=Scope.APP, groups=[G])
    container.open()
    with pytest.raises(exceptions.CircularDependencyError):
        container.resolve(_A)


def test_validate_walks_the_same_edges_resolve_follows() -> None:
    """INVARIANT: the graph validate() walks is the graph resolve() follows.

    Edges come from `WiringPlan.edges`, a view derived from the same buckets resolve() reads, so a
    provider named in a declaration-time `kwargs={...}` is an edge like any type-matched one.
    Assembling the validation edge set separately would let the two drift, and a cycle routed
    through a `kwargs=` provider would surface as a bare RecursionError instead.
    """

    class _Leaf: ...

    class _Root:
        def __init__(self, leaf: _Leaf) -> None:
            self.leaf = leaf  # pragma: no cover - validate() never instantiates providers

    class G(Group):
        leaf = Factory(scope=Scope.REQUEST, creator=_Leaf)
        # Named via kwargs, not type-matched: the by-type pass skips a name present in kwargs,
        # so this edge exists only if the overlay pass feeds it into WiringPlan.edges.
        root = Factory(scope=Scope.APP, creator=_Root, kwargs={"leaf": leaf})

    container = Container(scope=Scope.APP, groups=[G])
    with pytest.raises(exceptions.ValidationFailedError) as caught:
        container.validate()

    assert any(isinstance(error, exceptions.InvalidScopeDependencyError) for error in caught.value.errors)
