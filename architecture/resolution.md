# Resolution

How `modern-di` wires an object graph from type hints — from the first `resolve()` call to the returned instance.

## Entry points

There are two ways to trigger resolution from a `Container`:

- `container.resolve(SomeType)` — resolves by type. Looks up `SomeType` in `providers_registry`; raises
  `ProviderNotRegisteredError` (with closest-match suggestions) if no provider is registered for that type. Then
  delegates to `resolve_provider`.
- `container.resolve_provider(provider)` — resolves by provider reference directly, skipping the registry lookup.

## Step 1 — Override short-circuit

`resolve_provider` is the single choke-point through which every resolution passes. Before touching scope or cache it
checks the override registry:

```python
if (
    self.overrides_registry.overrides
    and (override := self.overrides_registry.fetch_override(provider.provider_id)) is not types.UNSET
):
    return override
```

The outer guard (`self.overrides_registry.overrides`) is a cheap truthiness check on a dict; `fetch_override` is only
called when at least one override exists. If an override is registered for this provider, it is returned immediately —
no scope walk, no cache check, no creator call.

## Step 2 — Scope walk (inside Factory.resolve)

After the override check, `resolve_provider` calls `provider.resolve(self)`. For `Factory` the first thing `resolve`
does is walk to the container at the provider's declared scope:

```python
container = container.find_container(self.scope)
```

`find_container` looks up `self.scope_map`, a dict built at container construction time that maps each scope level to
the container at that level. If the scope is deeper than the current container (not yet initialized) a
`ScopeNotInitializedError` is raised; if it was skipped when building the child chain, a `ScopeSkippedError` is raised.
From this point all cache and context operations use the scope-correct container.

## Step 3 — Cache hit

With the correct container in hand, `Factory.resolve` fetches (or creates) a `CacheItem` for this provider:

```python
cache_item = container.cache_registry.fetch_cache_item(self)

if self.cache_settings and cache_item.cache is not types.UNSET:
    return cache_item.cache
```

If `cache_settings` is configured **and** the cache slot already holds a value, the cached instance is returned
immediately. (A `Factory` with no `cache_settings` always re-runs the creator.)

## Step 4 — kwargs compilation

If no cached instance is returned, `Factory` compiles the keyword arguments needed to call the creator. This is done
once per container per provider via `_ensure_kwargs_cached`, which stores the split result on `CacheItem` so subsequent
calls (within the same container lifetime) skip recompilation.

Compilation is **type matching only** — it decides *which* provider (if any) backs each parameter, not what value that
provider currently holds. It therefore never goes stale and is never invalidated. `_compile_kwargs` iterates over
`_parsed_kwargs` — the `SignatureItem` map produced at provider-declaration time by `types_parser.parse_creator` — and
sorts each parameter into one of three buckets stored on the `CacheItem`:

1. **Static kwarg shadows** — if the parameter was supplied via the provider's declaration-time `kwargs`, it is taken
   from there. Provider-valued static kwargs go to `provider_kwargs`; plain values go to `static_kwargs`. These bypass
   type-based wiring.

2. **Provider lookup** — otherwise `_find_dep_provider` searches `providers_registry` for a provider matching the
   parameter's resolved type (`arg_type`) or, for union types, any of the union members (`args`); self-references are
   excluded. A matching `ContextProvider` goes to `context_kwargs` (resolved live, see Step 5); any other provider goes
   to `provider_kwargs`.

3. **No provider found** — this is a static graph fact, decided once here:
   - If the parameter has a default, it is omitted (the creator's own default applies).
   - If `SignatureItem.is_nullable` is `True` (the annotation included `None`, e.g. `X | None` or `Optional[X]`), it is
     set to `None` in `static_kwargs`.
   - Otherwise, `ArgumentResolutionError` is raised.

The three buckets — `provider_kwargs` (regular providers, resolved recursively), `static_kwargs` (plain values), and
`context_kwargs` (`ContextProvider` + its `SignatureItem`, resolved live) — are memoized so subsequent resolves within
the same container lifetime skip recompilation.

## Step 5 — Recursive resolution

With compiled kwargs in hand:

```python
resolved_kwargs = dict(static_kwargs)
for k, v in provider_kwargs.items():
    resolved_kwargs[k] = container.resolve_provider(v)
for k, (context_provider, item) in context_kwargs.items():
    value = self._resolve_context_value(container, k, context_provider, item)
    if value is not types.UNSET:
        resolved_kwargs[k] = value
```

Regular dependency providers are resolved by calling back into `container.resolve_provider`, which re-enters this same
sequence from Step 1 — override check, then `provider.resolve(container)`.

Context-backed parameters are resolved **live on every resolve**, so a `set_context` after a factory has already
resolved is always picked up (across scopes, for non-cached factories). `_resolve_context_value` mirrors
`resolve_provider`'s override check, then reads the live context value; when the value is absent it applies the same
fallback as Step 4's no-provider case — omit (default applies), `None` (nullable), or raise `ArgumentResolutionError`.

The recursion bottoms out at providers with
no dependencies or at already-cached instances.

## Step 6 — Creator call and caching

```python
instance = self._call_creator(resolved_kwargs)
```

If `cache_settings` is `None`, the instance is returned immediately with no caching. If `cache_settings` is set, a
lock (when `use_lock=True`) guards a double-checked read of the cache slot to handle concurrent first-resolves, then
the instance is stored and returned.

## Nullable wiring

`types_parser.SignatureItem` carries an `is_nullable: bool` field. It is set to `True` when the parameter annotation
is a union that includes `NoneType` — that is, `X | None`, `Optional[X]`, or any union spelled with `typing.Union`
that contains `None`. When `_compile_kwargs` cannot find a provider for the parameter (or finds a `ContextProvider`
with no value set) and the parameter has no default, `is_nullable=True` causes `None` to be injected rather than
raising an error.

## Thread safety

When `use_lock=True` (the default), the container holds a `threading.RLock`. The lock is acquired only around the
cache-write critical section inside `Factory.resolve` — kwargs compilation and recursive resolution happen outside the
lock. The double-checked locking pattern ensures that if two threads race to resolve the same uncached provider, only
one calls the creator and the other uses the freshly stored result.
