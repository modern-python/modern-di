# modern-di

A zero-dependency Python dependency-injection framework: it wires object graphs
from type annotations, manages lifetimes through a hierarchy of scopes, and runs
sync or async finalizers at close.

## Language

A term is listed only when there is a synonym to reject, or a meaning subtle enough that code and
docs must agree on it. General programming vocabulary does not belong here, however heavily this
project uses it.

**Container**:
Owns the registries and resolves within a scope.
_Avoid_: injector

**Provider**:
A declaration of *how to produce* a dependency; the recipe, not the value.
_Avoid_: service, dependency

**Scope**:
One band in the container hierarchy.
_Avoid_: lifetime, layer

**Group**:
A non-instantiable namespace class declaring providers.
_Avoid_: module

**Resolution**:
Producing a value from its provider.
_Avoid_: injection (reserve that for passing a resolved value into a handler)

**Override**:
A test-time replacement of a resolved value. An override supplies a concrete value; it does not
wrap or spy.
_Avoid_: mock, patch

**Bound type**:
The type a provider is registered under.
_Avoid_: registered type, return type

**Wiring plan**:
The partition of a creator's parameters by how each is satisfied.
_Avoid_: compiled kwargs

**Finalizer**:
A cleanup callback on a cached provider, run LIFO at close.
_Avoid_: teardown, destructor

**Connection**:
The framework object a unit of work carries.
_Avoid_: request (too HTTP-specific)
