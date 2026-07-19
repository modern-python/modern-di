# ruff: noqa: ANN001, ANN201
"""Guard tier — validate() graph-traversal cost.

`Container.validate()` walks the whole provider graph (cycle detection + transitive-scope
checks). It memoizes on the providers registry, so it does full work only once per registry;
G10/G11 use `benchmark.pedantic` with a per-round setup that builds a fresh unvalidated
container (untimed) and time `validate()` alone. 3.0 runs validate() by default at root
construction, so this is a real startup cost; G10 guards the deep-chain traversal, G11 the
wide fan-out. See benchmarks/README.md.
"""

import dataclasses

from modern_di import Container, Group, Scope, providers


# --- G10 subject: depth-6 chain (mirrors G3) -------------------------------
@dataclasses.dataclass(slots=True)
class C5:
    pass


@dataclasses.dataclass(slots=True)
class C4:
    c5: C5


@dataclasses.dataclass(slots=True)
class C3:
    c4: C4


@dataclasses.dataclass(slots=True)
class C2:
    c3: C3


@dataclasses.dataclass(slots=True)
class C1:
    c2: C2


@dataclasses.dataclass(slots=True)
class C0:
    c1: C1


class ChainGroup(Group):
    c5 = providers.Factory(creator=C5, scope=Scope.APP)
    c4 = providers.Factory(creator=C4, scope=Scope.APP)
    c3 = providers.Factory(creator=C3, scope=Scope.APP)
    c2 = providers.Factory(creator=C2, scope=Scope.APP)
    c1 = providers.Factory(creator=C1, scope=Scope.APP)
    c0 = providers.Factory(creator=C0, scope=Scope.APP)


def test_g10_validate_deep_chain(benchmark):
    good = Container(scope=Scope.APP, groups=[ChainGroup], validate=True)  # raises if invalid
    assert isinstance(good.resolve_provider(ChainGroup.c0), C0)
    benchmark.pedantic(
        lambda c: c.validate(),
        setup=lambda: ((Container(scope=Scope.APP, groups=[ChainGroup], validate=False),), {}),
        rounds=3000,
        iterations=1,
    )


# --- G11 subject: one object, 10 sibling deps (mirrors G4) ------------------
@dataclasses.dataclass(slots=True)
class L0:
    pass


@dataclasses.dataclass(slots=True)
class L1:
    pass


@dataclasses.dataclass(slots=True)
class L2:
    pass


@dataclasses.dataclass(slots=True)
class L3:
    pass


@dataclasses.dataclass(slots=True)
class L4:
    pass


@dataclasses.dataclass(slots=True)
class L5:
    pass


@dataclasses.dataclass(slots=True)
class L6:
    pass


@dataclasses.dataclass(slots=True)
class L7:
    pass


@dataclasses.dataclass(slots=True)
class L8:
    pass


@dataclasses.dataclass(slots=True)
class L9:
    pass


@dataclasses.dataclass(slots=True)
class Wide:
    l0: L0
    l1: L1
    l2: L2
    l3: L3
    l4: L4
    l5: L5
    l6: L6
    l7: L7
    l8: L8
    l9: L9


class WideGroup(Group):
    l0 = providers.Factory(creator=L0, scope=Scope.APP)
    l1 = providers.Factory(creator=L1, scope=Scope.APP)
    l2 = providers.Factory(creator=L2, scope=Scope.APP)
    l3 = providers.Factory(creator=L3, scope=Scope.APP)
    l4 = providers.Factory(creator=L4, scope=Scope.APP)
    l5 = providers.Factory(creator=L5, scope=Scope.APP)
    l6 = providers.Factory(creator=L6, scope=Scope.APP)
    l7 = providers.Factory(creator=L7, scope=Scope.APP)
    l8 = providers.Factory(creator=L8, scope=Scope.APP)
    l9 = providers.Factory(creator=L9, scope=Scope.APP)
    wide = providers.Factory(creator=Wide, scope=Scope.APP)


def test_g11_validate_wide(benchmark):
    good = Container(scope=Scope.APP, groups=[WideGroup], validate=True)  # raises if invalid
    assert isinstance(good.resolve_provider(WideGroup.wide), Wide)
    benchmark.pedantic(
        lambda c: c.validate(),
        setup=lambda: ((Container(scope=Scope.APP, groups=[WideGroup], validate=False),), {}),
        rounds=3000,
        iterations=1,
    )
