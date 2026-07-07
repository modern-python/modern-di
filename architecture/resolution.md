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
how each is satisfied. This is done once per container per provider via `_ensure_plan`, which stores a single
`WiringPlan` on the `CacheItem` so subsequent calls (within the same container lifetime) reuse it.

`WiringPlan.build` (in `modern_di/wiring.py`) is a **pure function** of `(parsed_kwargs, kwargs, providers_registry,
owner)` — it reads no cache, scope, or live context, so it runs outside the container lock and never goes stale (the
providers registry is fixed after construction). It is **type matching only**: it decides *which* provider (if any)
backs each parameter, not what value that provider currently holds. It iterates `_parsed_kwargs` — the `SignatureItem`
map produced at provider-declaration time by `types_parser.parse_creator` — and sorts each parameter:

1. **Static kwarg shadows** — if the parameter was supplied via the provider's declaration-time `kwargs`, it is taken
   from there. Provider-valued static kwargs go to the plan's `provider_kwargs`; plain values go to `static_kwargs`.
   These bypass type-based wiring and are *not* recorded in the plan's `dependencies` view, so `validate()` does not
   traverse them.

2. **Provider lookup** — otherwise `find_dep_provider` searches `providers_registry` for a provider matching the
   parameter's resolved type (`arg_type`) or, for union types, any of the union members (`args`); self-references are
   excluded. A matching `ContextProvider` goes to `context_kwargs` (resolved live, see Step 5); any other provider goes
   to `provider_kwargs`. Type-matched providers are also recorded in the plan's `dependencies` view, which `validate()`
   reads.

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

The plan's buckets — `provider_kwargs` (regular providers, resolved recursively), `static_kwargs` (plain values), and
`context_kwargs` (`ContextProvider` + its `SignatureItem`, resolved live) — plus the `dependencies` view and the
`unwireable` records are memoized on the `CacheItem`. The same `WiringPlan.build` backs `validate()`: `get_dependencies`
reads `dependencies`, `iter_validation_issues` builds a fresh error per `unwireable` record.

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

## Step 6 — Creator call and caching

`Factory` calls the creator with `resolved_kwargs`. With no `cache_settings`, the instance is returned immediately.
Otherwise the cache-write is guarded by the double-checked locking pattern described under
[Thread safety](#thread-safety) below, then the instance is stored and returned.

## Thread safety

When `use_lock=True` (the default), the container holds a `threading.RLock`. The lock is acquired only around the
cache-write critical section inside `Factory.resolve` — kwargs compilation and recursive resolution happen outside the
lock. The double-checked locking pattern ensures that if two threads race to resolve the same uncached provider, only
one calls the creator and the other uses the freshly stored result.
