# Resolution

How `modern-di` wires an object graph from type hints — from the first `resolve()` call to the returned instance.

Resolution runs through **one path**: a per-provider **compiled resolver** — a flat closure built once and
memoized. There is no interpreted fallback in the shipped tree; every provider type compiles.

## Entry points

- `container.resolve(SomeType)` — looks up `SomeType` in `providers_registry` (raising
  `ProviderNotRegisteredError`, with closest-match suggestions, if none is registered), then delegates to
  `resolve_provider`.
- `container.resolve_provider(provider)` — resolves by provider reference directly, skipping the registry lookup.
  It reopens the entry container if it was closed (see [containers.md](containers.md#closing)), then calls
  `providers_registry.resolver_for(provider)(self)` and wraps any escaped `RecursionError` (the runtime cycle
  guard — see [validation.md](validation.md)). It does **not** check overrides, scope, or cache centrally: each
  compiled resolver owns those checks itself.

## Compiled resolvers

`ProvidersRegistry.resolver_for(provider)` returns the provider's compiled resolver — a `Callable[[Container], T]`
built on first request by `resolver_compiler.compile_resolver` and then **memoized**, keyed by `provider_id` and
stamped with the `ProvidersRegistry.version` it was built against, exactly like `plan_for` (Step 4). A stamp
mismatch (the registry mutated since, e.g. after `add_providers`) rebuilds. Because a container and every child
share one registry, a resolver is compiled once per registry version for the whole tree.

`compile_resolver` dispatches on the provider's concrete type and returns a purpose-built closure:

- **`Factory`** — a transient resolver (no `cache_settings`) or a cached resolver.
- **`Alias`** — forwards to its source's resolver.
- the auto-registered **container provider** — returns the resolving container.
- **`ContextProvider`** — delegates to the bound `ContextProvider.resolve` (so its unset-value warning stays
  identical).
- a **`Factory` with an unwireable parameter** — an always-raising resolver (see Step 5).
- any other (unknown) provider type raises `TypeError` at compile time — the single place a new provider type
  is rejected until a branch is added for it.

### Cycle-safe compilation

`compile_resolver` captures each dependency's resolver *by reference* while it builds, so a resolver holds direct
callables to its dependencies' resolvers — the recursion of the old interpreted path is now a chain of closure
calls. To compile these back-edges safely, `resolver_for` marks a provider as *building* before it recurses; a
back-edge to a provider whose resolver is still under construction (a cycle) captures a **thunk** that routes
through the runtime `resolve_provider` instead of a half-built closure. A genuine cycle therefore still overflows
the stack at resolve time and is converted to `CircularDependencyError` by the runtime guard — the same salvage
`validate()` would surface up front (see [validation.md](validation.md)).

## Per-node shape

Every compiled resolver has the same front matter, in this order:

1. **Override live-guard.** The resolver checks the override registry *first* — but only when
   `overrides_registry.has_overrides` is set (the common no-overrides case skips even the lookup). An override
   registered for this provider is returned immediately: no scope walk, no cache check, no creator call. Because
   the check lives in each resolver rather than centrally, overriding an otherwise-unwireable factory (Step 5)
   still short-circuits to the mock.

2. **Scope navigation.** The resolver walks to the container at the provider's declared scope. The common
   same-scope case (`container.scope == scope`) skips `find_container` via an int compare; only a cross-scope
   dependency calls `_navigate`, which raises `ScopeNotInitializedError` / `ScopeSkippedError` (with this
   provider's step prepended) as appropriate — see [scopes.md](scopes.md) for the rule. A cross-scope **target**
   that is independently closed is reopened here (the entry container was already reopened by `resolve_provider`).

3. **Inlined build + call.** The resolver builds the creator's arguments by calling its dependencies' resolvers
   by reference and calls the creator — both inlined into the closure body (see Step 5, Step 6).

The container provider skips step 2 (it resolves to whichever container is asking); the `ContextProvider` and
`Alias` resolvers keep step 1 then delegate the rest to their reused bodies.

## Step 4 — Wiring plan

The **wiring plan** — the partition of the creator's parameters by how each is satisfied — is consulted when a
`Factory`'s resolver is compiled (once per registry version), not on each resolve. `Factory._plan` delegates to
`ProvidersRegistry.plan_for`, which memoizes one `WiringPlan` per
provider on the **registry** — keyed by `provider_id`, stamped with the `ProvidersRegistry.version` it was built
against. A call reuses the plan while that stamp matches the registry's current version and rebuilds when the registry
has changed (i.e. after `add_providers`). Because a container and every child share one `providers_registry`, the plan
is built once per registry version for the whole tree, not once per child container; a `REQUEST`-scoped factory
resolved across many child containers plans only once. `get_dependencies` and `iter_validation_issues` route through the
same memo, so `validate()` warms it rather than rebuilding on each graph walk.

`WiringPlan.build` (in `modern_di/wiring.py`) is a **pure function** of `(parsed_kwargs, kwargs, providers_registry,
owner)` — it reads no cache, scope, or live context, so it runs outside the container lock; the version stamp keeps the
memoized result from going stale against a mutated registry. It is **type matching only**: it decides *which* provider (if any)
backs each parameter, not what value that provider currently holds. It iterates `_parsed_kwargs` — the `SignatureItem`
map produced at provider-declaration time by `types_parser.parse_creator` — and sorts each parameter:

1. **Static kwarg shadows** — if the parameter was supplied via the provider's declaration-time `kwargs`, it is taken
   from there. Provider-valued static kwargs go to the plan's `provider_kwargs`; plain values go to `static_kwargs`.
   These bypass *type-based wiring* — the declaration names the provider outright instead of inferring it — but they are
   dependencies like any other, and `validate()` traverses them.

2. **Provider lookup** — otherwise `find_dep_provider` searches `providers_registry` for a provider matching the
   parameter's resolved type (`arg_type`) or, for union types, any of the union members (`args`); self-references are
   excluded. A matching `ContextProvider` goes to `context_kwargs` (resolved live, see Step 5); any other provider goes
   to `provider_kwargs`.

   > **Union vs. single parameterized generics.** A bare parameterized generic (e.g. `list[str]`) is *rejected at
   > declaration* — it cannot be resolved by type. Inside a union, however, each member degrades to its origin for
   > matching, so `int | list[str]` matches a provider registered for plain `list`. The element type is not enforced
   > (Python ignores it at runtime); this asymmetry is intentional, not a wiring guarantee.

3. **No provider found** — a static graph fact, decided once via the shared `absent_disposition(item)` helper (the
   single home of the absent-value table — also applied live in Step 5, for an unset context value):
   - If the parameter has a default, it is omitted (the creator's own default applies).
   - Else if `SignatureItem.is_nullable` is `True` (the annotation included `None`, e.g. `X | None` or `Optional[X]`),
     `None` is placed in `static_kwargs`.
   - Otherwise the parameter is recorded in the plan's `unwireable` list as a `(name, SignatureItem)` record — **not** a
     pre-built exception (see Step 5).

   > A bare `None` annotation is the **degenerate nullable** — a union with zero non-`None` members — and takes the
   > same two branches as `X | None`: `x: None = None` omits (its default applies), and `x: None` injects `None`,
   > which is the annotation's only legal value. `SignatureItem.from_type` handles `NoneType` in its own branch, since
   > the union branch would otherwise take it for a plain type and look `NoneType` up in the registry. In the *return*
   > position (`-> None`, a void creator) the nullability is simply unread: only `.arg_type` is consulted, to derive
   > `bound_type`.

The plan's buckets — `provider_kwargs` (regular providers, resolved recursively), `static_kwargs` (plain values), and
`context_kwargs` (`ContextProvider` + its `SignatureItem`, resolved live) — plus the `unwireable` records make up the
`WiringPlan` memoized on the `ProvidersRegistry`. The same `WiringPlan.build` backs `validate()`: `get_dependencies` returns
`plan.edges`, `iter_validation_issues` builds a fresh error per `unwireable` record.

> **One edge set.** `WiringPlan.edges` is a *derived* view — `provider_kwargs` merged with the providers out of
> `context_kwargs` — not a fourth bucket `build` fills in. Because it is computed from the same buckets `resolve()`
> reads, the graph `validate()` traverses cannot drift from the graph that actually resolves: a provider named in a
> declaration-time `kwargs={...}` is an edge exactly like a type-matched one. (Before this was unified, such an edge
> was invisible to `validate()`, so a cycle routed through `kwargs=` passed validation and then died at resolve time
> with a raw `RecursionError`.)
>
> A provider cannot be passed to *its own* `kwargs=` — the reference does not exist yet at declaration — so a cycle
> made purely of static kwargs is unconstructible; every `kwargs=` cycle needs at least one type-matched edge to
> close it. That is why `find_dep_provider` excludes the owner (a self-reference by type is dropped, not an edge)
> while `kwargs=` needs no such exclusion.

## Step 5 — Recursive resolution

**Unwireable first.** When the plan has an unwireable parameter, the whole graph is broken at compile time, so
the resolver compiled for it is a dedicated **always-raising** closure (`_compile_unwireable_factory`): after the
override guard and scope navigation it raises a **freshly built** `ArgumentResolutionError` from the first
`unwireable` record. The error is built fresh on every call (never memoized) because `prepend_step` (owned by the
shared `DependencyPathMixin`, mixed into both `ResolutionError` and the two scope errors) *mutates* the exception
as it propagates up the chain — a stored instance would accumulate and leak breadcrumbs across repeated or nested
resolves. This mirrors what the old interpreted `Factory._resolve_kwargs` did on its unwireable branch, now
decided once at compile time rather than re-checked on every resolve.

**Dependencies.** A wireable resolver builds the creator's arguments inside a single `try` that prepends this
provider's step to any `ResolutionError` / scope error escaping from below (so the failing provider's name makes
it into the breadcrumb even though the deps resolve outside a per-dep try):

- Each `provider_kwargs` entry is resolved by calling its dependency's **compiled resolver directly** (captured
  by reference at compile time) — the chain of closure calls that replaces the old per-edge `resolve_provider`
  recursion. A back-edge into a still-compiling provider was captured as a thunk that re-enters `resolve_provider`
  (see [Cycle-safe compilation](#cycle-safe-compilation)).
- Each `context_kwargs` entry is resolved **live**, on every resolve, via the reused `Factory._resolve_context_value`
  — so a `set_context` after a factory has already resolved is still picked up (across scopes, for non-cached
  factories). `_resolve_context_value` runs its own override check, then reads the live context value; when it is
  absent, the shared `absent_disposition` helper applies — omit (default applies), `None` (nullable), or raise
  `ArgumentResolutionError` — the same three-way disposition Step 4 computes statically for a missing provider,
  just evaluated live instead of once at plan-build time.
- `static_kwargs` (plain literal values) are folded in as-is.

The recursion bottoms out at providers with no dependencies or at already-cached instances.

### Guarded positional fast path

When the whole parsed signature is provider dependencies in declaration order — nothing static, context,
default-omitted, keyword-only, or positional-only, and no `kwargs=` overlay extra — the resolver calls the creator
**positionally** (`creator(v0, v1, …)`), skipping the measured 4–6× `**kwargs` cost. `_positional_names` is the
compile-time predicate that decides eligibility; when in doubt it excludes, and the resolver keeps
`creator(**kwargs)`. The negative cases matter: a keyword-only parameter, or a positional-only parameter dropped
from `_parsed_kwargs` by the parser, would shift or reject positional binding, so both keep the kwargs call.

### Breadcrumb definition sites

Each step a `Factory` prepends onto a breadcrumb chain may carry an optional definition site — the
creator's declaration point, rendered as a trailing `module:line` anchor — alongside the provider
name. The site is captured lazily, only when a step is actually being built on an error path, and
memoized per provider so a repeated failure never re-inspects the creator. Capture is best-effort:
a plain function or method resolves for free from its code object, a class falls back to source
inspection, and anything without an inspectable source (C callables, `functools.partial`, and the
like) yields no site rather than raising. `Alias` steps never carry a definition site, since an
alias has no creator of its own to anchor.

### One renderer

Every glyph in every message lives in `exceptions.py`, and nowhere else. Two private drawers own the
formatting the errors share:

- `_render_chain(steps)` draws a `list[ResolutionStep]` as the indented arrow tree with an aligned
  scope column. It is the single home of the chain glyphs, used by both `DependencyPathMixin`
  (a resolution breadcrumb) and `CircularDependencyError` (a cycle) — which is why the two read
  identically and cannot drift.
- `_render_suggestions(items)` draws the `Did you mean:` block from `list[suggester.Suggestion]`.
  It is the single home of the suggestion glyphs, used by `ProviderNotRegisteredError`,
  `ArgumentResolutionError`, and `UnknownFactoryKwargError`.

What crosses into an error is **facts, never formatting**. `suggester.suggest(requested_type, providers)`
returns `Suggestion` records — `(name, reason, scope)` — not rendered bullets, so `.suggestions` on a
caught exception is data a caller can act on rather than glyphs it would have to parse back apart.
An error also derives whatever it can from what it was already handed: `InvalidChildScopeError`
computes `.allowed_scopes` from `parent_scope`, and `UnknownFactoryKwargError` runs its own
`close_matches` over the `unknown_keys`/`known_keys` it receives. Neither is computed at a raise site.

`suggester` owns what a suggestion *is* (the `Suggestion` record) and how to *find* one —
`suggest` holds the policy (hierarchy hints, typo matching, cap, ordering) over a registry's providers,
and `close_matches` is the shared difflib primitive. `ProvidersRegistry` is pure storage; `exceptions`
owns how everything *looks*. The messages themselves stay inline
f-strings in the class that raises them — only the shared glyph logic is factored out, not the
message catalog (see [2026-06-23.02-inline-error-messages](../planning/changes/2026-06-23.02-inline-error-messages.md)).

Rendered error text is diagnostic, not a public contract; the structured attributes and the class
hierarchy are. See [2026-07-14-error-text-is-not-a-contract](../planning/decisions/2026-07-14-error-text-is-not-a-contract.md).

## Step 6 — Creator call and caching

The resolver calls the creator with the built arguments. A `TypeError` from the call is handled by a `tb_next`
guard reused across every resolver (and by `Factory._call_creator`, which the cached kwargs path still reuses):
an argument-binding failure (no inner traceback frame) is wrapped in a `CreatorCallError` with this provider's
step prepended, while a `TypeError` raised *inside* the creator body (inner frame present) propagates unchanged,
like any other error.

- **Transient** (no `cache_settings`) — the built instance is returned immediately; the creator re-runs on every
  resolve.
- **Cached** — the resolver first checks the cache slot: a **warm hit** returns the stored instance directly,
  skipping the `get_or_create` frame. On a **cold miss** it builds the arguments and calls the creator under the
  cache lock (the double-checked locking pattern under [Thread safety](#thread-safety)), stores the result, and
  marks it in the container's creation order so finalizers run LIFO on close (see
  [containers.md](containers.md#closing)).

## Thread safety

When `use_lock=True` (the default), the container holds a `threading.RLock`. The lock is acquired only around the
cache-write critical section (inside `CacheItem.get_or_create`) — argument building and recursive resolution
happen outside the lock. The double-checked locking pattern ensures that if two threads race to resolve the same
uncached provider, only one calls the creator and the other uses the freshly stored result.
