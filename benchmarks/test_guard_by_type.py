# ruff: noqa: ANN001, ANN201
"""Guard tier — by-type resolution (`resolve(SomeType)`), the integration/`@inject` path.

Every other guard scenario resolves by provider reference (`resolve_provider`), which skips
the `find_provider` lookup that by-type resolution pays on each call. G16 isolates that lookup
on a small graph; G17 repeats it against a 200-provider registry so the cost is guarded at the
scale a real application registers, not just at the 2-11 providers the other scenarios use.
Containers are built and warmed in setup; only the resolve is timed. See benchmarks/README.md.
"""

import dataclasses

from modern_di import Container, Group, Scope, providers


# --- G16 subject graph: the G1/G2 shape, resolved by type ------------------
@dataclasses.dataclass(slots=True)
class Dep:
    pass


@dataclasses.dataclass(slots=True)
class Service:
    dep: Dep


class ByTypeGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP, cache=True)
    svc = providers.Factory(creator=Service, scope=Scope.APP, cache=True)


def test_g16_resolve_by_type(benchmark):
    container = Container(scope=Scope.APP, groups=[ByTypeGroup])
    container.open()
    container.resolve(Service)  # warm the cache and the compiled resolver
    result = benchmark(container.resolve, Service)
    assert isinstance(result, Service)
    assert isinstance(result.dep, Dep)


# --- G17 subject graph: the same resolve against a 200-provider registry ----
_REGISTRY_SIZE = 200
_FILLER_TYPES = [
    dataclasses.dataclass(slots=True)(type(f"Filler{i}", (), {"__annotations__": {}})) for i in range(_REGISTRY_SIZE)
]
_WIDE_REGISTRY_GROUP = type(
    "WideRegistryGroup",
    (Group,),
    {
        **{f"f{i}": providers.Factory(creator=t, scope=Scope.APP, cache=True) for i, t in enumerate(_FILLER_TYPES)},
        "dep": providers.Factory(creator=Dep, scope=Scope.APP, cache=True),
        "svc": providers.Factory(creator=Service, scope=Scope.APP, cache=True),
    },
)


def test_g17_resolve_by_type_large_registry(benchmark):
    # Same resolve as G16 with 200 unrelated providers registered: guards find_provider at the
    # scale a real app registers. A regression here that G16 misses is a lookup-scaling regression.
    container = Container(scope=Scope.APP, groups=[_WIDE_REGISTRY_GROUP])
    container.open()
    container.resolve(Service)  # warm
    result = benchmark(container.resolve, Service)
    assert isinstance(result, Service)
    assert isinstance(result.dep, Dep)
