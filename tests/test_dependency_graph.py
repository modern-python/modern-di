"""Event-stream tests for ``DependencyGraph.walk`` — the module's test surface is the event SEQUENCE."""

from modern_di import Container, Scope
from modern_di.dependency_graph import (
    Cycle,
    DependenciesError,
    DependencyGraph,
    Edge,
    NodeEntered,
)
from modern_di.group import Group
from modern_di.providers import Alias, Factory


class Leaf: ...


class Root:
    def __init__(self, leaf: Leaf) -> None: ...


# Module-level so the forward reference resolves (a class-local "CycB" would not).
class CycA:
    def __init__(self, b: "CycB") -> None: ...


class CycB:
    def __init__(self, a: CycA) -> None: ...


def test_walk_emits_node_then_edge_then_child() -> None:
    class G(Group):
        root = Factory(scope=Scope.APP, creator=Root)
        leaf = Factory(scope=Scope.APP, creator=Leaf)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    events = list(DependencyGraph().walk([G.root, G.leaf], c))
    kinds = [type(e).__name__ for e in events]
    assert kinds[0] == "NodeEntered"
    assert "Edge" in kinds
    # leaf visited exactly once even though it's both a root and a dependency
    assert sum(isinstance(e, NodeEntered) and e.provider is G.leaf for e in events) == 1


def test_walk_full_sequence_preorder() -> None:
    class G(Group):
        root = Factory(scope=Scope.APP, creator=Root)
        leaf = Factory(scope=Scope.APP, creator=Leaf)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    events = list(DependencyGraph().walk([G.root], c))
    assert events == [
        NodeEntered(G.root),
        Edge(G.root, "leaf", G.leaf),
        NodeEntered(G.leaf),
    ]


def test_walk_emits_cycle_closing_on_first_node() -> None:
    class G(Group):
        a = Factory(scope=Scope.APP, creator=CycA)
        b = Factory(scope=Scope.APP, creator=CycB)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    cycles = [e for e in DependencyGraph().walk([G.a], c) if isinstance(e, Cycle)]
    assert cycles
    assert cycles[0].providers[0].provider_id == cycles[0].providers[-1].provider_id


def test_walk_cycle_edge_precedes_cycle_and_no_descent() -> None:
    class G(Group):
        a = Factory(scope=Scope.APP, creator=CycA)
        b = Factory(scope=Scope.APP, creator=CycB)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    events = list(DependencyGraph().walk([G.a], c))
    assert events == [
        NodeEntered(G.a),
        Edge(G.a, "b", G.b),
        NodeEntered(G.b),
        Edge(G.b, "a", G.a),
        Cycle([G.a, G.b, G.a]),
    ]


def test_walk_visited_dep_not_re_entered() -> None:
    class Shared: ...

    class L:
        def __init__(self, s: Shared) -> None: ...

    class R:
        def __init__(self, s: Shared) -> None: ...

    class G(Group):
        left = Factory(scope=Scope.APP, creator=L)
        right = Factory(scope=Scope.APP, creator=R)
        shared = Factory(scope=Scope.APP, creator=Shared)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    events = list(DependencyGraph().walk([G.left, G.right], c))
    # Shared is a dep of both roots but entered exactly once.
    assert sum(isinstance(e, NodeEntered) and e.provider is G.shared for e in events) == 1
    # Both roots still emit the Edge to the shared dep; the second finds it visited, no re-descent.
    edges_to_shared = [e for e in events if isinstance(e, Edge) and e.dep is G.shared]
    assert [e.parent for e in edges_to_shared] == [G.left, G.right]


def test_walk_root_already_visited_is_skipped_entirely() -> None:
    class G(Group):
        root = Factory(scope=Scope.APP, creator=Root)
        leaf = Factory(scope=Scope.APP, creator=Leaf)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    # leaf appears as a dep of root (first root) AND as a later root; the later root is skipped.
    events = list(DependencyGraph().walk([G.root, G.leaf], c))
    assert sum(isinstance(e, NodeEntered) and e.provider is G.leaf for e in events) == 1


def test_find_cycle_from_returns_none_when_acyclic() -> None:
    class G(Group):
        leaf = Factory(scope=Scope.APP, creator=Leaf)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    assert DependencyGraph().find_cycle_from(G.leaf, c) is None


def test_find_cycle_from_returns_loop() -> None:
    class G(Group):
        a = Factory(scope=Scope.APP, creator=CycA)
        b = Factory(scope=Scope.APP, creator=CycB)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    cycle = DependencyGraph().find_cycle_from(G.a, c)
    assert cycle == [G.a, G.b, G.a]


def test_terminal_scope_follows_alias_chain() -> None:
    class ChainTerminal: ...

    class ChainMid: ...

    class ChainTop: ...

    class G(Group):
        terminal = Factory(scope=Scope.REQUEST, creator=ChainTerminal)
        mid = Alias(source_type=ChainTerminal, bound_type=ChainMid)
        top = Alias(source_type=ChainMid, bound_type=ChainTop)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    assert DependencyGraph().terminal_scope(G.top, c) == Scope.REQUEST


def test_terminal_scope_alias_cycle_falls_back_to_self_scope() -> None:
    class MutualX: ...

    class MutualY: ...

    class G(Group):
        a = Alias(source_type=MutualY, bound_type=MutualX)
        b = Alias(source_type=MutualX, bound_type=MutualY)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    assert DependencyGraph().terminal_scope(G.a, c) == G.a.scope


def test_walk_dangling_dep_emits_dependencies_error() -> None:
    class Missing: ...

    class Marker: ...

    class G(Group):
        # Bound under Marker, sourced from the unregistered Missing -> get_dependencies raises.
        alias = Alias(Missing, bound_type=Marker)

    c = Container(scope=Scope.APP, groups=[G], validate=False)
    events = list(DependencyGraph().walk([G.alias], c))
    assert isinstance(events[0], NodeEntered)
    assert events[0].provider is G.alias
    assert isinstance(events[1], DependenciesError)
    assert events[1].provider is G.alias
    # dangling alias contributes no edges past the error
    assert not any(isinstance(e, Edge) for e in events)
