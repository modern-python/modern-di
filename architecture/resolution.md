# Resolution

How `modern-di` wires an object graph from type hints. This page states what must stay true of the
resolve path; `modern_di/resolver_compiler.py` and `modern_di/wiring.py` are where it is currently
made true.

## Entry points

- `container.resolve(SomeType)` — looks up `SomeType` in `providers_registry` (raising
  `ProviderNotRegisteredError`, with closest-match suggestions, if none is registered), then dispatches to the
  compiled resolver itself. It holds its own copy of `resolve_provider`'s body rather than delegating, so the
  by-type path pays no extra frame; the two copies must be edited together
  ([decision](../planning/decisions/2026-08-03-resolve-provider-not-a-seam.md)).
- `container.resolve_provider(provider)` — resolves by provider reference, skipping the registry lookup.
  It reopens the entry container if it was closed (see [containers.md](containers.md#closing)), then calls
  `providers_registry.resolver_for(provider)(self)` and wraps any escaped `RecursionError` (the runtime cycle
  guard — see [validation.md](validation.md)).

## Compiled resolvers

Resolution runs through **one path**: a per-provider **compiled resolver**, a flat
`Callable[[Container], T]` built once by `compile_resolver` and memoized on the registry by
`provider_id`. No interpreted fallback ships.

The memo is cleared whenever the registry mutates, so the next call rebuilds. A container and every
child share one registry, so a resolver is compiled once for the whole tree.

### Cycle-safe compilation

Compilation captures each dependency's resolver **by reference**, so a resolver holds direct callables
to its dependencies rather than recursing through `resolve_provider`. To close back-edges safely,
`resolver_for` marks a provider as *building* before it recurses: a back-edge into a provider whose
resolver is still under construction captures a **thunk** that routes through the runtime
`resolve_provider` instead of a half-built closure. A genuine cycle therefore still overflows the
stack at resolve time and is converted to `CircularDependencyError` by the runtime guard — the same
salvage `validate()` surfaces up front (see [validation.md](validation.md)).

## Invariants

These hold regardless of how the compiler is structured. A change that breaks one is a behaviour
change, not a refactor.

- **One frame per node.** A resolved node costs one Python frame. This is why the override guard is
  inlined into every closure rather than checked centrally, why the kwargs build and creator call are
  inlined, and why a warm cache hit returns without entering `get_or_create`. Any extraction that adds
  a per-node frame trades against this budget.
- **Override wins first.** Every resolver front-guards the override registry before scope navigation,
  before the cache, and before the creator. Overriding an otherwise-unwireable factory still
  short-circuits to the supplied value. The guard is skipped entirely when no overrides are registered.
- **Navigate once.** A resolver walks to the container at its declared scope exactly once per resolve;
  the same-scope case is an int compare, not a lookup. Cross-scope navigation raises
  `ScopeNotInitializedError` / `ScopeSkippedError` with this provider's step prepended (see
  [scopes.md](scopes.md)). A cross-scope target that is independently closed is reopened there.
- **One graph.** The wiring plan that `resolve()` reads is the same plan `validate()` traverses, so the
  validated graph cannot drift from the resolved one. A provider named in a declaration-time
  `kwargs={...}` is an edge exactly like a type-matched one.
- **Context is live.** A `ContextProvider` dependency is read on every resolve, so a later `set_context`
  is picked up by non-cached factories across scopes. A cached factory is built once and does not
  re-read it.
- **Errors are built fresh, never memoized.** `prepend_step` *mutates* the exception as it propagates,
  so a stored instance would accumulate breadcrumbs across repeated or nested resolves.
- **Behaviour-sensitive helpers are reused, not reimplemented.** `_resolution_step`, `prepend_step`,
  `ContextProvider.resolve`, and `CreatorCallError.from_type_error` have one home each; the compiler
  calls them rather than inlining their semantics. The **context-kwarg lookup is the deliberate
  exception**: it is folded into each compiled closure, and the helper it replaced was deleted rather
  than left alongside, so the semantics still have exactly one home per closure instead of two homes
  to keep in step. Its licence is that a registered `ContextProvider`'s scope and `context_type` are
  fixed — see [providers.md](providers.md#contextprovider--runtime-injected-values).
- **A new provider type fails loudly.** `compile_resolver` raises `TypeError` for any type it has no
  branch for — the single place an unsupported provider is rejected.

## Wiring plan

The **wiring plan** partitions a creator's parameters by how each is satisfied. It is consulted when a
`Factory`'s resolver is compiled, not on each resolve, and is memoized per provider on the registry
alongside the resolver.

`WiringPlan.build` is a **pure function** of `(parsed_kwargs, kwargs, providers_registry, owner)`: it
reads no cache, scope, or live context, so it runs outside the container lock. It is **type matching
only** — it decides *which* provider backs each parameter, never what value that provider holds. Each
parameter lands in one of four places:

- **`static_kwargs`** — supplied via the provider's declaration-time `kwargs`, or filled with `None`
  for an absent nullable dependency.
- **`provider_kwargs`** — matched to a provider by resolved type, or named outright in `kwargs=`.
  Self-references are excluded.
- **`context_kwargs`** — matched to a `ContextProvider`; resolved live.
- **`unwireable`** — no provider, no default, not nullable. Recorded as a `(name, SignatureItem)` fact,
  not a pre-built exception. Such a factory compiles to an always-raising resolver, since the graph is
  broken before any resolve happens.

Absence is decided once, by the shared `absent_disposition` helper: default → omit, nullable → `None`,
otherwise unwireable. The same helper applies live when a context value turns out to be unset, so the
static and live paths cannot disagree.

Two matching rules are subtle enough to state outright:

- A bare parameterized generic (`list[str]`) is **rejected at declaration** — it cannot be resolved by
  type. Inside a union, each member degrades to its origin, so `int | list[str]` matches a provider
  registered for plain `list`. The element type is not enforced; this asymmetry is intentional and is
  not a wiring guarantee.
- A bare `None` annotation is the **degenerate nullable** — a union with zero non-`None` members — and
  takes the same branches as `X | None`. In the *return* position (`-> None`) nullability is unread;
  only `arg_type` is consulted, to derive `bound_type`.

## Positional fast path

When the whole parsed signature is provider dependencies in declaration order — nothing static,
context, default-omitted, keyword-only, or positional-only, and no `kwargs=` overlay extra — the
creator is called positionally, skipping the measured 4–6× `**kwargs` cost.

The eligibility predicate is deliberately conservative: **when in doubt it excludes**, and the resolver
keeps `creator(**kwargs)`. This is an optimization that must never change binding semantics, so the
negative cases matter more than the positive one — a keyword-only parameter, or a positional-only
parameter dropped from `_parsed_kwargs` by the parser, would shift or reject positional binding, and
both keep the kwargs call.

Arity 0 and 1 compile to a closure that names its argument and calls the creator directly, instead of
building a list and star-calling it; arity 2+ keeps the star-call. See
[performance.md](performance.md#the-per-node-frame-budget) for why the ladder stops there.

### Transient teardown order is unspecified

**The order in which transient dependencies are collected is not part of the contract.** It is only
observable at all for a dependency the creator does *not* retain — one it uses and drops — where the
resolver briefly holds the only reference. modern-di manages no finalizer for such an object:
`CacheSettings(finalizer=)` applies to cached providers, and `close_sync` / `close_async` to what a
container owns. An unretained transient is freed by CPython's ordinary refcounting, and the resolver's
shape decides the order.

That shape changed with the arity ladder, and **not uniformly across versions**: the star-call's
intermediate list frees back-to-front on every interpreter, while the ladder's named locals are
released with the frame — same back-to-front order on 3.14, but front-to-back on 3.10. Code that
depends on `__del__` ordering for unretained injected dependencies was relying on an accident of the
call convention, and never on anything stated here.

## Breadcrumb definition sites

Each step a `Factory` prepends onto a breadcrumb chain may carry an optional definition site — the
creator's declaration point, rendered as a trailing `module:line` anchor — alongside the provider name.
The site is captured lazily, only when a step is actually being built on an error path, and memoized
per provider so a repeated failure never re-inspects the creator. Capture is best-effort: a plain
function or method resolves for free from its code object, a class falls back to source inspection, and
anything without an inspectable source (C callables, `functools.partial`) yields no site rather than
raising. `Alias` steps never carry a definition site, since an alias has no creator of its own.

## One renderer

Every glyph in every message lives in `exceptions.py`, and nowhere else. Two private drawers own the
shared formatting:

- `_render_chain(steps)` draws a `list[ResolutionStep]` as the indented arrow tree with an aligned
  scope column — used by both `DependencyPathMixin` (a resolution breadcrumb) and
  `CircularDependencyError` (a cycle), which is why the two cannot drift.
- `_render_suggestions(items)` draws the `Did you mean:` block from `list[suggester.Suggestion]` — used
  by `ProviderNotRegisteredError`, `ArgumentResolutionError`, and `UnknownFactoryKwargError`.

What crosses into an error is **facts, never formatting**. `suggester.suggest` returns `Suggestion`
records — `(name, reason, scope)` — so `.suggestions` on a caught exception is data a caller can act on
rather than glyphs it would have to parse back apart. An error derives what it can from what it was
handed: `InvalidChildScopeError` computes `.allowed_scopes` from `parent_scope`, and
`UnknownFactoryKwargError` runs its own `close_matches`. Neither is computed at a raise site. Messages
stay inline f-strings in the class that raises them; only the shared glyph logic is factored out.

Rendered error text is diagnostic, not a public contract; the structured attributes and the class
hierarchy are. See
[2026-07-14-error-text-is-not-a-contract](../planning/decisions/2026-07-14-error-text-is-not-a-contract.md).

## Thread safety

When `use_lock=True` (the default), the container holds a `threading.RLock`, acquired **only** around
the cache-write critical section. Argument building and recursive resolution happen outside it. The
double-checked locking pattern ensures that if two threads race to resolve the same uncached provider,
only one calls the creator and the other uses the freshly stored result.
