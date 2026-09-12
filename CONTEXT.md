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

**Effective scope**:
The band a provider actually resolves in, once any redirection to another provider is followed. The
same as the provider's own scope unless it redirects, where the provider at the end of the chain
governs.
_Avoid_: terminal scope

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

**Resolver shape**:
The parts of a Factory that decide its generated resolver source: arity or kwarg names, static
kwargs, context kwargs, cached. Factories of one shape share a code object.
_Avoid_: template (that is the source the shape is rendered into), signature

**Finalizer**:
A cleanup callback on a cached provider, run LIFO at close.
_Avoid_: teardown, destructor

**Connection**:
The framework object a unit of work carries.
_Avoid_: request (too HTTP-specific)
