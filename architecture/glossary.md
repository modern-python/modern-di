# Glossary

The project's ubiquitous language — the domain terms worth pinning down: those
with a synonym to reject, or a meaning subtle enough that code, specs, and
capability pages must agree on it. Not an exhaustive dictionary of every class
name; a term earns a place when there is something to disambiguate, and entries
are authored lazily as that need arises. Living prose, no frontmatter, dated by
git. Each entry says what a term *is* (not what it does) and links to the
capability page that owns the behaviour; an _Avoid_ line names the synonyms to
reject. No implementation detail; this is a glossary, not a spec.

**Container**:
The central object: it owns the provider registries and resolves dependencies
within a scope. Containers form a parent→child hierarchy, one per scope band. See
[containers.md](containers.md).
_Avoid_: injector

**Provider**:
A declaration of *how to produce* a dependency — the recipe, not the value.
`Factory`, `Alias`, and `ContextProvider` are the concrete kinds. See
[providers.md](providers.md).
_Avoid_: service, dependency (those name the produced value, not its recipe)

**Scope**:
One band in the container hierarchy (`APP → SESSION → REQUEST → ACTION → STEP`),
ordered shallow to deep; a provider resolves only from a container at the same or
a deeper band. See [scopes.md](scopes.md).
_Avoid_: lifetime, layer

**Group**:
A non-instantiable namespace class whose class attributes declare providers. See
[providers.md](providers.md).
_Avoid_: module

**Resolution**:
The act of producing a dependency's value from its provider, wiring the
provider's own dependencies from their type hints. Sync-only (async resolution
was removed in 2.x). See [resolution.md](resolution.md).
_Avoid_: injection (reserve that for the integration act of passing a resolved
value into a handler)

**Validation**:
A static check of the provider graph — cycles plus scope ordering — run before
resolution, without calling any creator. See [validation.md](validation.md).

**Override**:
A test-time replacement of a provider's resolved value with a supplied object,
short-circuiting its creator. See
[testing-and-overrides.md](testing-and-overrides.md).
_Avoid_: mock, patch (an override supplies a concrete value; it does not wrap or spy)

**Child container**:
A container built at a deeper scope from a parent. It shares the parent's
providers and overrides registries but owns its own cache and context. See
[containers.md](containers.md).

**Bound type**:
The type a provider is registered under and resolvable by — taken from the
creator's return annotation unless set explicitly. See
[resolution.md](resolution.md).
_Avoid_: registered type, return type

**Wiring plan**:
The partition of a creator's parameters by how each is satisfied — a provider, a
static value, a context lookup, or unwireable. A pure function of the provider
and the registry's contents. See [resolution.md](resolution.md).
_Avoid_: compiled kwargs

**Finalizer**:
A cleanup callback bound to a cached provider, run when the container closes
(LIFO); may be sync or async. See [containers.md](containers.md).
_Avoid_: teardown, destructor

**Connection**:
The framework-specific object a unit of work carries — an HTTP request, a
broker message, a CLI invocation's context. Not every unit of work has one (a
Typer command's underlying callable does not).
_Avoid_: request (too HTTP-specific — a broker message is also a connection)

**Connection match**:
A child container's derived `scope` and `context`, produced by binding a
connection to one `ContextProvider`. See
[integration-kit.md](integration-kit.md).

**Integration kit**:
The framework-agnostic primitives (`modern_di.integrations`) an integration
adapter composes to derive connection scope/context and to run the
`Annotated`-marker injector, instead of hand-rolling either. See
[integration-kit.md](integration-kit.md).
