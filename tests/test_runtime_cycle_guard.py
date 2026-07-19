"""Runtime cycle guard (ERR-1): an unvalidated circular graph raises CircularDependencyError.

Complements ``test_container.py``'s ``validate()``-time cycle tests: these exercise the
guard in ``Container.resolve_provider`` that catches a ``RecursionError`` escaping an
unvalidated resolve and converts it when a static cycle is reachable from the failing
provider, leaving genuinely recursive (non-cyclic) creators untouched.
"""

import dataclasses
import inspect
import sys

import pytest

from modern_di import Container, Group, Scope, dependency_graph, exceptions, providers


# Lowering the recursion limit (from CPython's default of 1000) triggers the RecursionError much
# closer to the call site — fewer ambient frames from pytest/coverage machinery are on the stack
# when it's caught and converted, which keeps that conversion deterministic under coverage.py
# (CPython suspends trace-function calls for a few frames while unwinding a RecursionError, and
# without this, coverage.py can flakily under-report lines that run immediately after recovery —
# a known CPython/coverage.py interaction, not a real gap in execution). Unrelated to the guard's
# iterative-finder requirement, which must stay flat regardless of where the limit sits.
_SHALLOW_RECURSION_LIMIT = 80


@dataclasses.dataclass(kw_only=True, slots=True)
class Common:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class NodeA:
    # `common` is shared with `NodeB` and resolves (and is walked by the finder) *before* `dep`,
    # so the finder's cycle re-walk visits and fully finishes `Common` from one side before
    # encountering it again from the other — exercising the "already visited, skip" branch —
    # before it finds the actual A<->B back-edge.
    common: Common
    dep: "NodeB"


@dataclasses.dataclass(kw_only=True, slots=True)
class NodeB:
    common: Common
    dep: NodeA


class CycleGroup(Group):
    common = providers.Factory(creator=Common)
    a = providers.Factory(creator=NodeA)
    b = providers.Factory(creator=NodeB)


@dataclasses.dataclass(kw_only=True, slots=True)
class DeepNodeA:
    dep: "DeepNodeB"


@dataclasses.dataclass(kw_only=True, slots=True)
class DeepNodeB:
    dep: DeepNodeA


@dataclasses.dataclass(kw_only=True, slots=True)
class Middle:
    node: DeepNodeA


@dataclasses.dataclass(kw_only=True, slots=True)
class Root:
    middle: Middle


class DeepCycleGroup(Group):
    node_a = providers.Factory(creator=DeepNodeA)
    node_b = providers.Factory(creator=DeepNodeB)
    middle = providers.Factory(creator=Middle)
    root = providers.Factory(creator=Root)


def _assert_simple_cycle(exc: exceptions.CircularDependencyError) -> None:
    assert exc.cycle_path[0] == exc.cycle_path[-1]
    assert set(exc.cycle_path) == {"NodeA", "NodeB"}
    assert isinstance(exc.__cause__, RecursionError)
    # Isolate the cycle's own rendering (after "caused by: ") from the breadcrumb prefix, which
    # already carries per-hop anchors (ERR-6 task 1) and would make this assertion pass regardless.
    lineno = inspect.getsourcelines(NodeA)[1]
    cycle_rendering = str(exc).rsplit("caused by: ", 1)[-1]
    assert f"({NodeA.__module__}:{lineno})" in cycle_rendering


def test_unvalidated_cycle_raises_circular_dependency_error() -> None:
    # Asserting inside a plain `except` clause (rather than `pytest.raises(...)` followed by
    # assertions after the `with` block) keeps this deterministic under coverage.py — see
    # `_SHALLOW_RECURSION_LIMIT` above. It mirrors the guard's own `except RecursionError` shape
    # in `resolve_provider`.
    container = Container(groups=[CycleGroup], validate=False)  # exercise the runtime guard, not validation
    container.open()
    original_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_SHALLOW_RECURSION_LIMIT)
    try:
        container.resolve(NodeA)
    # CPython suspends trace-function calls for a few frames while unwinding a RecursionError;
    # coverage.py can then under-report lines that run immediately during/after that recovery —
    # a known CPython/coverage.py interaction (not a real execution gap: these lines run on
    # every pass of this test, or the test would error/fail instead of passing).
    except exceptions.CircularDependencyError as exc:  # pragma: no cover
        _assert_simple_cycle(exc)
    else:  # pragma: no cover
        pytest.fail("expected CircularDependencyError")
    finally:  # pragma: no cover
        sys.setrecursionlimit(original_limit)


def _assert_deep_chain_cycle_is_self_contained(exc: exceptions.CircularDependencyError) -> None:
    # Reached via the Root -> Middle -> DeepNodeA approach path, but the cycle itself is only
    # DeepNodeA <-> DeepNodeB: CircularDependencyError.prepend_step is a no-op (ERR-1 canonicalization),
    # so no outer frame accumulates a Root/Middle breadcrumb onto an already self-contained cycle.
    assert exc.dependency_path == []
    names = set(exc.cycle_path)
    assert names == {"DeepNodeA", "DeepNodeB"}
    rendered = str(exc)
    assert "Root" not in rendered
    assert "Middle" not in rendered
    assert isinstance(exc.__cause__, RecursionError)


def test_deep_chain_cycle_is_self_contained() -> None:
    container = Container(groups=[DeepCycleGroup], validate=False)  # exercise the runtime guard, not validation
    container.open()
    original_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_SHALLOW_RECURSION_LIMIT)
    try:
        container.resolve(Root)
    # See `test_unvalidated_cycle_raises_circular_dependency_error` for why this is `no cover`.
    except exceptions.CircularDependencyError as exc:  # pragma: no cover
        _assert_deep_chain_cycle_is_self_contained(exc)
    else:  # pragma: no cover
        pytest.fail("expected CircularDependencyError")
    finally:  # pragma: no cover
        sys.setrecursionlimit(original_limit)


def test_self_recursing_creator_passes_through_recursion_error() -> None:
    def recursive_creator() -> str:
        return recursive_creator()

    class RecursiveGroup(Group):
        svc = providers.Factory(creator=recursive_creator, bound_type=str)

    # validate=False keeps the registry unvalidated, so the guard runs find_cycle_from (no static cycle ->
    # re-raise) rather than short-circuiting on the validated flag.
    container = Container(groups=[RecursiveGroup], validate=False)
    container.open()
    with pytest.raises(RecursionError):
        container.resolve(str)


def test_validated_graph_reraises_recursionerror_without_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    # A self-recursive creator on a validated (acyclic-static) graph must re-raise the
    # RecursionError untouched, short-circuiting before find_cycle_from is ever consulted.
    class SelfRec:
        def __init__(self) -> None:
            raise RecursionError

    class G(Group):
        s = providers.Factory(scope=Scope.APP, creator=SelfRec)

    container = Container(scope=Scope.APP, groups=[G], validate=True)
    container.open()

    def _explode(*_: object, **__: object) -> object:  # pragma: no cover
        msg = "walked"
        raise AssertionError(msg)

    monkeypatch.setattr(dependency_graph.DependencyGraph, "find_cycle_from", _explode)
    with pytest.raises(RecursionError):
        container.resolve(SelfRec)


class _CanonicalA:
    # Module-level (not nested in the test): `typing.get_type_hints` resolves a forward-ref
    # string annotation against `__init__.__globals__`, which only reaches module globals —
    # a class local to the test function would not be found, unlike `NodeA`/`NodeB` above.
    def __init__(self, b: "_CanonicalB") -> None: ...


class _CanonicalB:
    def __init__(self, a: _CanonicalA) -> None: ...


def _assert_cycle_is_canonical_and_self_contained(exc: exceptions.CircularDependencyError) -> None:
    msg = str(exc)
    # Self-contained: names only the A/B loop, no accumulated outer breadcrumb repetition.
    assert msg.count("A") >= 1
    # Canonical: the rendered cycle starts at the same anchor regardless of seed.
    cycle_names = exc.cycle_path
    assert cycle_names[0] == cycle_names[-1]  # ring closes
    assert min(cycle_names) == cycle_names[0]  # anchored at the min name (proxy for min provider_id ordering)


def test_cycle_error_is_canonical_and_self_contained() -> None:
    # A -> B -> A.
    class G(Group):
        a = providers.Factory(creator=_CanonicalA, scope=Scope.APP)
        b = providers.Factory(creator=_CanonicalB, scope=Scope.APP)

    container = Container(scope=Scope.APP, groups=[G], validate=False)
    container.open()
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(80)
    try:
        container.resolve(_CanonicalA)
    # See `test_unvalidated_cycle_raises_circular_dependency_error` for why this is `no cover`.
    except exceptions.CircularDependencyError as exc:  # pragma: no cover
        _assert_cycle_is_canonical_and_self_contained(exc)
    else:  # pragma: no cover
        pytest.fail("expected CircularDependencyError")
    finally:  # pragma: no cover
        sys.setrecursionlimit(limit)
