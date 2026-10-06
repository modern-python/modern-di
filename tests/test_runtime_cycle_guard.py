"""Runtime cycle guard (ERR-1): an unvalidated circular graph raises CircularDependencyError.

Complements ``test_container.py``'s ``validate()``-time cycle tests: these exercise the
guard in ``Container.resolve_provider`` that catches a ``RecursionError`` escaping an
unvalidated resolve and converts it when a static cycle is reachable from the failing
provider, leaving genuinely recursive (non-cyclic) creators untouched.
"""

import dataclasses
import inspect
import sys
import threading

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
    container = Container(groups=[CycleGroup])  # exercise the runtime guard, not validation
    original_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_SHALLOW_RECURSION_LIMIT)
    try:
        container.resolve(NodeA)
    except exceptions.CircularDependencyError as exc:
        _assert_simple_cycle(exc)
    else:
        pytest.fail("expected CircularDependencyError")
    finally:
        sys.setrecursionlimit(original_limit)


class CachedCycleGroup(Group):
    common = providers.Factory(creator=Common, cache=True)
    a = providers.Factory(creator=NodeA, cache=True)
    b = providers.Factory(creator=NodeB, cache=True)


def _resolve_in_daemon_thread(container: Container) -> BaseException | None:
    """Resolve `NodeA` on a daemon thread under the shallow limit; return what it raised, or None if it hung."""
    raised: list[BaseException] = []

    def worker() -> None:
        try:
            container.resolve(NodeA)
        except Exception as exc:  # noqa: BLE001
            raised.append(exc)

    original_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_SHALLOW_RECURSION_LIMIT)
    try:
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=5)
    finally:
        sys.setrecursionlimit(original_limit)
    return raised[0] if raised else None


def test_cached_cycle_reenters_the_item_lock_and_raises_circular_dependency_error() -> None:
    """A same-thread cycle through cached factories re-enters each item's lock and still raises.

    The second resolve runs on another thread, so it hangs instead of raising if the first left
    an item's lock held.
    """
    container = Container(groups=[CachedCycleGroup])
    for _ in range(2):
        exc = _resolve_in_daemon_thread(container)
        assert isinstance(exc, exceptions.CircularDependencyError)
        _assert_simple_cycle(exc)


def _assert_deep_chain_cycle_is_self_contained(exc: exceptions.CircularDependencyError) -> None:
    # Reached via the Root -> Middle -> DeepNodeA approach path, but the cycle itself is only
    # DeepNodeA <-> DeepNodeB: CircularDependencyError._prepend_step is a no-op (ERR-1 canonicalization),
    # so no outer frame accumulates a Root/Middle breadcrumb onto an already self-contained cycle.
    assert exc.dependency_path == []
    names = set(exc.cycle_path)
    assert names == {"DeepNodeA", "DeepNodeB"}
    rendered = str(exc)
    assert "Root" not in rendered
    assert "Middle" not in rendered
    assert isinstance(exc.__cause__, RecursionError)


def test_deep_chain_cycle_is_self_contained() -> None:
    container = Container(groups=[DeepCycleGroup])  # exercise the runtime guard, not validation
    original_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_SHALLOW_RECURSION_LIMIT)
    try:
        container.resolve(Root)
    except exceptions.CircularDependencyError as exc:
        _assert_deep_chain_cycle_is_self_contained(exc)
    else:
        pytest.fail("expected CircularDependencyError")
    finally:
        sys.setrecursionlimit(original_limit)


def test_self_recursing_creator_passes_through_recursion_error() -> None:
    def recursive_creator() -> str:
        return recursive_creator()

    class RecursiveGroup(Group):
        svc = providers.Factory(creator=recursive_creator, bound_type=str)

    # The registry starts unvalidated (nothing here calls validate()), so the guard runs
    # find_cycle_from (no static cycle -> re-raise) rather than short-circuiting on the validated flag.
    container = Container(groups=[RecursiveGroup])
    with pytest.raises(RecursionError):
        container.resolve(str)


def test_validated_graph_reraises_recursionerror_without_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    """INVARIANT: on a validated graph an escaped RecursionError re-raises untouched.

    A validated graph is known acyclic, so the overflow is genuine self-recursion in a creator.
    Walking anyway would misreport it as a circular dependency and burn stack near the limit.
    """

    class SelfRec:
        def __init__(self) -> None:
            raise RecursionError

    class G(Group):
        s = providers.Factory(scope=Scope.APP, creator=SelfRec)

    container = Container(scope=Scope.APP, groups=[G])
    container.validate()  # marks the graph validated -> the recursion guard short-circuits below

    def _explode(*_: object, **__: object) -> object:
        msg = "walked"
        raise AssertionError(msg)

    monkeypatch.setattr(dependency_graph, "find_cycle_from", _explode)
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

    container = Container(scope=Scope.APP, groups=[G])
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(80)
    try:
        container.resolve(_CanonicalA)
    except exceptions.CircularDependencyError as exc:
        _assert_cycle_is_canonical_and_self_contained(exc)
    else:
        pytest.fail("expected CircularDependencyError")
    finally:
        sys.setrecursionlimit(limit)


def test_by_reference_cycle_raises_circular_dependency_error() -> None:
    # By-reference twin of the by-type test above, and the only guard on `resolve_provider`'s
    # own conversion: `Container.resolve` carries a second copy, so replacing the conversion
    # here with a bare re-raise still passes every by-type cycle test. This is a behavioural
    # guard, not a coverage one -- the line is covered by
    # `test_by_reference_recursionerror_passes_through`, which reaches it without an overflow.
    # Same `except`-clause shape and shallow limit, per `_SHALLOW_RECURSION_LIMIT`.
    container = Container(groups=[CycleGroup])
    original_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_SHALLOW_RECURSION_LIMIT)
    try:
        container.resolve_provider(CycleGroup.a)
    except exceptions.CircularDependencyError as exc:
        _assert_simple_cycle(exc)
    else:
        pytest.fail("expected CircularDependencyError")
    finally:
        sys.setrecursionlimit(original_limit)


def test_by_reference_recursionerror_passes_through() -> None:
    # Reaches `resolve_provider`'s handler WITHOUT a stack overflow, so the trace function is
    # still alive and the line is recorded on CPython below 3.12. The by-type twin of this
    # (`test_validated_graph_reraises_recursionerror_without_walk`) now lands on `resolve`'s
    # own copy of the handler, leaving this entry point otherwise untraced.
    class SelfRec:
        def __init__(self) -> None:
            raise RecursionError

    class G(Group):
        s = providers.Factory(scope=Scope.APP, creator=SelfRec)

    container = Container(scope=Scope.APP, groups=[G])
    container.validate()
    with pytest.raises(RecursionError):
        container.resolve_provider(G.s)
