# Resolution

How `modern-di` wires an object graph from type hints — from the first `resolve()` call to the returned instance.

## Entry points

- `container.resolve(SomeType)` — looks up `SomeType` in `providers_registry` (raising
  `ProviderNotRegisteredError`, with closest-match suggestions, if none is registered), then delegates to
  `resolve_provider`.
- `container.resolve_provider(provider)` — resolves by provider reference directly, skipping the registry lookup.

## Step 1 — Override short-circuit

`resolve_provider` is the single choke-point every resolution passes through, and the override registry is
checked first — before scope or cache. An override, if registered for this provider, is returned immediately:
no scope walk, no cache check, no creator call.

## Step 2 — Scope walk (inside Factory.resolve)

`Factory.resolve` walks to the container at the provider's declared scope via `find_container`, raising
`ScopeNotInitializedError` or `ScopeSkippedError` as appropriate — see [scopes.md](scopes.md) for the rule and
error conditions. From this point all cache and context operations use the scope-correct container.

`Factory.resolve` wraps its own `find_container` call and prepends its own step on a scope error before
re-raising, so the failing provider's name makes it into the breadcrumb chain even though this call sits outside
the try block that wraps the rest of `resolve` (see Step 5's `prepend_step` note for the general mechanism).
`Alias.resolve`'s except is widened the same way.

## Step 3 — Cache hit

If `cache_settings` is configured **and** the cache slot already holds a value, the cached instance is returned
immediately. A `Factory` with no `cache_settings` always re-runs the creator.

## Step 4 — Wiring plan

If no cached instance is returned, `Factory` builds the **wiring plan**: the partition of the creator's parameters by
how each is satisfied. `Factory._plan` delegates to `ProvidersRegistry.plan_for`, which memoizes one `WiringPlan` per
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
`WiringPlan` memoized on the `CacheItem`. The same `WiringPlan.build` backs `validate()`: `get_dependencies` returns
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

`Factory` first surfaces any unwireable parameter: if `plan.unwireable` is non-empty it raises a **freshly built**
`ArgumentResolutionError` from the first record before calling the creator. The error is built fresh on every raise
(never memoized) because `prepend_step` (owned by the shared `DependencyPathMixin`, mixed into both
`ResolutionError` and the two scope errors) *mutates* the exception as it propagates up the chain — a stored
instance would accumulate and leak breadcrumbs across repeated or nested resolves.

Each `provider_kwargs` entry is resolved by calling back into `container.resolve_provider`, re-entering this same
sequence from Step 1. Each `context_kwargs` entry is resolved **live**, on every resolve, via
`_resolve_context_value` — so a `set_context` after a factory has already resolved is still picked up (across
scopes, for non-cached factories). `_resolve_context_value` mirrors `resolve_provider`'s override check, then reads
the live context value; when it is absent, the shared `absent_disposition` helper applies — omit (default
applies), `None` (nullable), or raise `ArgumentResolutionError` — the same three-way disposition Step 4 computes
statically for a missing provider, just evaluated live instead of once at plan-build time.

The recursion bottoms out at providers with no dependencies or at already-cached instances.

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

`Factory` calls the creator with `resolved_kwargs`. With no `cache_settings`, the instance is returned immediately.
Otherwise the cache-write is guarded by the double-checked locking pattern described under
[Thread safety](#thread-safety) below, then the instance is stored and returned.

## Thread safety

When `use_lock=True` (the default), the container holds a `threading.RLock`. The lock is acquired only around the
cache-write critical section inside `Factory.resolve` — kwargs compilation and recursive resolution happen outside the
lock. The double-checked locking pattern ensures that if two threads race to resolve the same uncached provider, only
one calls the creator and the other uses the freshly stored result.
