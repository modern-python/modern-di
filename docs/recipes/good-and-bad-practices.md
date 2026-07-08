# Good and bad practices

modern-di's docs mostly show the happy path. This page collects the footguns instead — real
mistakes the framework lets you make, each paired with the mechanism that catches or prevents it.

## 1. Captive dependency: a wide-scoped provider holding a narrow-scoped one

A *captive dependency* is a wide-scoped provider holding a narrow-scoped one it cannot actually
outlive — see [the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) for why.

```python
class Dependencies(Group):
    session = providers.Factory(Session, scope=Scope.REQUEST)

    # ❌ forgot scope=Scope.REQUEST — defaults to Scope.APP, which cannot hold `session`
    user_cache = providers.Factory(UserCache)

    # ✅ matches the lifetime of what it consumes
    user_cache = providers.Factory(UserCache, scope=Scope.REQUEST)
```

**Caught by:** `Container(groups=[...], validate=True)` raises `InvalidScopeDependencyError` for
this exact graph before anything is ever resolved — see
[Scope chain violation](../troubleshooting/scope-chain.md). If the graph is never validated, the
runtime failure is a `ScopeNotInitializedError`/`ScopeSkippedError` that (since the scope-error
breadcrumb work) now names both the provider that captured the dependency and the one that
actually failed — but it fires on the first request that hits it, not at startup. Prefer catching it
statically.

## 2. Shipping a never-validated graph

`validate()` is the only thing that checks the *whole* graph — cycles, inverted scopes, and missing
dependencies — before the first request. Skipping it doesn't remove the bugs, it just delays
finding them to whichever resolve happens to hit one first.

```python
# ❌ wiring bugs surface one at a time, in production, on whatever request trips them
container = Container(groups=[Dependencies])

# ✅ every wiring bug in the graph is reported at startup, all at once
container = Container(groups=[Dependencies], validate=True)
```

**Caught by:** `validate=True` (or an explicit `container.validate()` call), which finds every
issue in the graph up front instead of one at a time. An unvalidated cyclic graph still isn't a
silent hang — see [the runtime cycle guard](../troubleshooting/circular-dependency.md#the-runtime-cycle-guard-without-validate).
Leaving `validate` unset on a root container also emits `UnvalidatedContainerWarning`, since
modern-di 3.0 turns validation on by default.

## 3. A cached factory resolved before `set_context`

Context values are read live on every resolve of a **non-cached** factory — but a **cached**
factory is built once, and a later `set_context` does not rebuild it.

```python
class Dependencies(Group):
    tenant_id = providers.ContextProvider(str, scope=Scope.REQUEST)

    # ❌ cached: built on first resolve and frozen from then on
    tenant_config = providers.Factory(create_tenant_config, scope=Scope.REQUEST, cache=True)

    # ✅ uncached: re-reads the live context on every resolve
    tenant_config = providers.Factory(create_tenant_config, scope=Scope.REQUEST)
```

If a request container resolves `tenant_config` before the real tenant ID is known (e.g. during
setup), the cached version keeps serving that first value for the rest of the request even after
`request.set_context(str, real_tenant_id)` runs. Either drop `cache=True` for anything whose
correctness depends on context set later, or make sure `set_context` runs before the first resolve.
**Caught by:** nothing automatic — this is a timing bug, not a wiring bug, so `validate()` cannot
see it. See [Context propagation](../providers/context.md#context-propagation) for how `set_context`
timing interacts with a provider's scope, and [Lifecycle](../providers/lifecycle.md) for caching.

## 4. Service location via `container_provider` overuse

`container_provider` lets a creator accept the resolving `Container` itself and pull dependencies
out of it manually. Used for its intended purpose (a provider that genuinely needs the container,
such as building a child container), it's fine. Used as a shortcut to avoid declaring real
parameters, it turns type-driven DI into a service locator: the dependency is hidden from
`validate()`, from readers, and from anyone trying to see the graph.

```python
# ❌ the real dependency (Settings) is invisible to validate() and to the signature
def create_api_key(container: Container) -> str:
    return container.resolve(Settings).api_key

# ✅ declared as an ordinary parameter — visible, validated, and testable via override
def create_api_key(settings: Settings) -> str:
    return settings.api_key
```

**Caught by:** nothing enforces this — it's a style discipline, not a validation rule. Reserve
`container_provider` for cases that are actually about the container (building a child container,
introspecting the current scope), and declare everything else as a typed parameter so
`validate()` and [Resolving dependencies](../introduction/resolving.md) can see it.

## 5. Override leaks across tests

`container.override(provider, replacement)` replacements are shared across the *whole* container
tree — see [Testing with overrides](testing-overrides.md) for the mechanics. Forgetting to reset
it doesn't just affect the test that set it — every later test that shares the container inherits
the replacement.

```python
# ❌ no reset: the next test that resolves Clock silently gets the fake
def test_one() -> None:
    container.override(Dependencies.clock, fake_clock)
    ...

# ✅ always reset, even if the test fails — a fixture teardown is the reliable place for this
@pytest.fixture
def frozen_clock() -> Mock:
    fake = Mock(spec=Clock)
    container.override(Dependencies.clock, fake)
    yield fake
    container.reset_override(Dependencies.clock)
```

**Caught by:** nothing automatic mid-suite — `reset_override(provider)` (or `reset_override()` with no
arguments, to clear everything) is the fix, and closing the **root** container clears every override
in the shared registry as a last resort. See
[Testing with overrides](testing-overrides.md#pitfalls).

## 6. `skip_creator_parsing=True` with no `bound_type`

`skip_creator_parsing=True` turns off signature introspection — useful for callables that can't be
reflected (C extensions, `functools.partial`). But skipping introspection also means modern-di has
no idea what type the provider produces, so type-based resolution silently can't find it.

```python
# ❌ nothing else can resolve this provider by type — UserWarning at declaration time
providers.Factory(opaque_creator, scope=Scope.APP, skip_creator_parsing=True)

# ✅ tell modern-di the type explicitly
providers.Factory(
    opaque_creator,
    scope=Scope.APP,
    skip_creator_parsing=True,
    bound_type=MyClass,
)
```

**Caught by:** a `UserWarning` at declaration time. It's easy to miss in test output — treat it as a
signal to add `bound_type=`, not to ignore.

## See also

- [Errors and exceptions](../providers/errors-and-exceptions.md) — the full catalog this page draws
  its mechanisms from.
- [Testing with overrides](testing-overrides.md) — the full override lifecycle.
- [Lifecycle](../providers/lifecycle.md) — caching, finalizers, and `validate()`.
