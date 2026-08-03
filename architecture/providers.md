# Provider Catalog

Every provider type in `modern-di`: what each one is, and the mechanism behind it. This page is the
truth home for the catalog, kept true by the promotion rule — a change to a provider's behaviour
edits this page in the same PR. `docs/providers/` covers how to use them.

---

## `Group` — provider namespace

`Group` is a non-instantiable base class. Attempting to instantiate it (or any subclass) raises
`GroupInstantiationError`. Its sole purpose is to act as a namespace for declaring providers as class-level
attributes:

```python
from modern_di import providers, Group, Scope


class AppProviders(Group):
    db_pool = providers.Factory(create_pool, scope=Scope.APP)
    user_repo = providers.Factory(UserRepository, scope=Scope.REQUEST)
```

`Group.get_named_providers()` walks the MRO and returns a `dict[str, AbstractProvider]` mapping each declared
attribute name to its provider — respecting inheritance order, de-duplicating by first-seen name, and letting a
non-provider override mask the parent provider of the same name. `Group.get_providers()` is derived from it as
`list(cls.get_named_providers().values())`, so the traversal and de-duplication rules live in one place.

### Group-level default scope

A `Group` subclass may declare a default scope as a class kwarg — `class RequestGroup(Group, scope=Scope.REQUEST)`.
At class creation, `Group.__init_subclass__` stamps that scope onto every scope-defaulted `Factory`/`ContextProvider`
declared in that class body. Priority: an explicit `scope=` on the provider always wins; otherwise the nearest
group `scope=` kwarg in the MRO applies (a subclass without its own kwarg inherits its ancestor's; a subclass with
its own kwarg overrides it for its own body); otherwise the provider falls back to `Scope.APP`. `Alias` never
participates in stamping — its scope is always derived from its source, never chosen (see below). A
scope-defaulted provider instance shared between two group bodies with different defaults raises
`GroupScopeConflictError` (a `RegistrationError` subclass) at the second group's class-creation time, rather than
letting import order decide; sharing the same instance with the same default scope across groups is a no-op.

A group body **without** a `scope=` kwarg stamps nothing, so a provider listed only there stays unclaimed and a
later group may still stamp it. That is sound only until the provider is registered: `add_providers`/`register`
set `AbstractProvider._registered`, and a compiled resolver captures `scope` in its closure, so a change after
that point would apply to later-compiled resolvers only. `_stamp_group_scope` therefore raises
`ProviderScopeFrozenError` when a stamp would *change* the scope of a registered provider. A same-scope stamp
still returns early and stays legal, so the shared-instance pattern above is unaffected. See
[docs/providers/scopes.md#group-level-default-scope](../docs/providers/scopes.md#group-level-default-scope) for
the user-facing walkthrough.

---

## `Factory` — the universal provider

`Factory` is the main building block. Every provider that calls a creator callable (a constructor or factory
function passed as its `creator` argument) is a `Factory`. Each registerable provider's subject argument —
`Factory.creator`, `ContextProvider.context_type`, `Alias.source_type` — is positional-or-keyword and leads its
`__init__`; every other parameter stays keyword-only.

### Signature

```python
Factory(
    creator: Callable[..., T],
    *,
    scope: IntEnum = UNSET,  # defaults to the group's scope, else Scope.APP
    bound_type: type | None = UNSET,
    kwargs: dict[str, Any] | None = None,
    cache: bool | CacheSettings[T] | None = None,
    skip_creator_parsing: bool = False,
)
```

### Declaration-time signature parsing

When `skip_creator_parsing=False` (the default), `Factory.__init__` calls `types_parser.parse_creator(creator)`
immediately. This extracts the return type (used as the provider's `bound_type` unless overridden) and a mapping
of parameter names to `SignatureItem` descriptors. Dependency resolution is therefore type-driven: at resolution
time each parameter is matched against the container's `providers_registry` by its annotated type.

If `bound_type` is supplied explicitly it overrides the inferred return type (useful when the creator returns a
protocol or base class narrower than the concrete type). See
[docs/providers/factories.md](../docs/providers/factories.md#creator-signature-support-matrix) for the full
per-parameter-shape behavior table (`UnsupportedCreatorParameterError` conditions, escape hatches, union
resolution order).

### Recursive resolution

A `Factory`'s parsed parameter map is partitioned into a wiring plan, and its compiled resolver calls
each dependency's resolver by reference — see [resolution.md](resolution.md#compiled-resolvers), which
owns the plan, the memoization, and the breadcrumb.

### Static kwargs and `skip_creator_parsing`

See [docs/providers/factories.md](../docs/providers/factories.md#kwargs) for `kwargs=` (static values,
overriding provider-resolved ones for the same key; an unknown key raises `UnknownFactoryKwargError` at
declaration time, unless the creator accepts `**kwargs` or its signature cannot be reflected) and
`skip_creator_parsing=True` (disables signature introspection; a `UserWarning` is
emitted if `bound_type` isn't given explicitly, since the provider then can't be resolved by type).

---

## `CacheSettings` — singleton behavior

There is no separate `Singleton` class — see [docs/providers/factories.md](../docs/providers/factories.md)
for the user-facing singleton idiom.

`CacheSettings` is a `dataclass` with the following fields:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `clear_cache` | `bool` | `True` | Whether the cached instance is evicted when the container closes. |
| `finalizer` | `Callable[[T], None \| Awaitable[None]] \| None` | `None` | Optional teardown called on container close, before cache eviction. |
| `is_async_finalizer` | `bool` | *(computed)* | Not an init parameter — derived by `inspect.iscoroutinefunction(finalizer)` in `__post_init__`. The container uses it to decide whether to `await` the finalizer. |

Without `cache`, a `Factory`'s resolver calls the creator on every resolution and returns a fresh instance
each time.

---

## `ContextProvider` — runtime-injected values

`ContextProvider` holds a value that is supplied at container-creation time via the `context` mapping rather than
being constructed by a factory:

```python
providers.ContextProvider(HttpRequest, scope=Scope.REQUEST)
```

At resolution time it looks the value up in the container's `context_registry` for the matching scope. What
happens next depends on **how** the value is fetched — direct resolve vs. as another provider's dependency —
and the two paths are independent:

- **Direct resolve** (`container.resolve(HttpRequest)` / `container.resolve_provider(the_provider)` →
  `ContextProvider.resolve`): if no value was supplied (the key is absent), it raises
  `ContextValueNotSetError`, naming the context type and the resolving container's scope — see
  [Migration: To 3.x](../docs/migration/to-3.x.md#5-direct-resolve-of-an-unset-contextprovider-raises).
  `ContextValueNoneWarning` still exists in `exceptions.py` (retained so existing
  `filterwarnings` configs don't break) but nothing raises it any more.
- **As a dependent parameter** of another provider (e.g. a `Factory` constructor argument typed as the context
  type): unaffected by the above — no exception is raised on this path. The compiled `Factory` closure does the
  whole lookup inline, applying `absent_disposition`'s ruling for an absent value: if the dependent parameter has
  a default or is nullable it is silently satisfied; otherwise an `ArgumentResolutionError` is raised.

**A `ContextProvider`'s identity is fixed once something has resolved through it.** Its `scope` and its
`context_type` are read when a consumer's resolver is compiled and folded into that closure, so changing either
afterwards applies only to resolvers compiled later — silently, since neither attribute touches a registry and
so nothing invalidates the memo. How much of that is *enforced* differs by attribute and by route:

- `scope` on a **registered** provider is enforced against group stamping by `ProviderScopeFrozenError`.
- `scope` on a provider that is never registered — one passed only as `Factory(creator, kwargs={"x": cp})` —
  is **not** enforced: `_registered` stays `False`, so a later `Group` may stamp it without error.
- `context_type` is not enforced on either route.

So this is a contract, not a mechanism: rebinding `provider.scope` or `provider.context_type` on a provider that
is already in use is unsupported. Construct a second provider instead.

Either **declaration route** reaches that dependent-parameter path: matched by type from the registry, or
passed explicitly as `Factory(creator, kwargs={"request": the_provider})`. `WiringPlan.build` buckets both
into `context_kwargs` with the parameter's `SignatureItem`, so the two agree — how the provider reaches the
parameter is a declaration detail, not a behavior switch.

The one exception is a `ContextProvider` passed via `kwargs={...}` for a parameter with **no parsed
`SignatureItem`** — a `**kwargs` creator, or `skip_creator_parsing=True`. There is no default or nullability
to consult, so it stays on the direct-resolve path above and raises `ContextValueNotSetError` when unset.
Treating it as required would raise where the parameter itself has no such constraint declared; treating it
as nullable would silently swallow the unset-context signal — so it keeps direct-resolve semantics instead.

`ContextProvider` also accepts an optional `bound_type` that overrides the inferred bound type.

---

## `Alias` — re-exporting a type under a different name

`Alias` delegates resolution to another registered provider, located by the source type:

```python
providers.Alias(ConcreteDatabase, bound_type=DatabaseProtocol)
```

The compiled `Alias` resolver calls its source's compiled resolver directly, after its own override guard — it
holds no cache of its own — wrapping a scope/resolution error with the alias's own step. The source lookup and
the source's resolver-memo read are inlined into the closure (see
[performance.md](performance.md#inlined-memo-hits)); nothing is cached there, so a source registered after the
alias first resolves is picked up on the next one. `Alias` also accepts an optional `bound_type` override. See
[docs/providers/alias.md](../docs/providers/alias.md) for the user-facing rationale and caching implications.

`Alias` overrides the `redirect_target(container)` node hook to return its source provider (`None` when the
source type is unregistered), marking the alias as a transparent redirect. `DependencyGraph.terminal_scope`
follows that hook down an alias chain to the terminal non-alias provider and returns that provider's scope —
which is what `Container.validate()` and scope-error reporting compare against (see
[validation.md](validation.md#terminal-scope-and-alias-transparency)). An alias's own scope is always `Scope.APP`
internally; its effective scope at resolution time is derived from its source provider's scope.

---

## `container_provider` — the container itself

A pre-built singleton, auto-registered in every container, that resolves to the `Container` asking for
it. See [containers.md](containers.md#container_provider) for its registration mechanics.
