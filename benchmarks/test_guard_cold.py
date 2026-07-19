# ruff: noqa: ANN001, ANN201
"""Guard tier — cold first-resolve (container build + graph compile).

G8 is the **one** guard scenario that builds the root container *inside* the
timed call: a fresh `Container(groups=[...])` has a fresh providers registry, so
the first resolve compiles the whole provider graph from scratch. Every other
guard file builds/warms in setup and times only the steady-state call; this one
deliberately measures construction + compile + resolve as a single unit, the
cost paid once per container in short-lived processes (serverless, CLI, tests)
and at every app startup. See benchmarks/README.md.
"""

import dataclasses

from modern_di import Container, Group, Scope, providers


# --- depth-6 chain subject graph (mirrors G3/C3, the largest compile signal) ---
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


def _cold_build_and_resolve() -> C0:
    # Fresh registry -> full compile every call: construction + open + first-resolve compile + resolve.
    container = Container(scope=Scope.APP, groups=[ChainGroup], validate=False)
    container.open()
    return container.resolve_provider(ChainGroup.c0)


def test_g8_cold_first_resolve(benchmark):
    result = benchmark(_cold_build_and_resolve)
    assert isinstance(result, C0)
    assert isinstance(result.c1.c2.c3.c4.c5, C5)
