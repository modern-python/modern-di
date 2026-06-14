# Errors and exceptions

Every exception `modern-di` raises lives in `modern_di.exceptions` and descends from a single
root, `ModernDIError`. The hierarchy is grouped by *when* the failure happens — registering
providers, validating the graph, resolving a type, or closing a container — so you can catch a
whole category with one `except`.

```python
from modern_di import exceptions
```

## Hierarchy

```
ModernDIError (RuntimeError)
├── ContainerError
│   ├── InvalidChildScopeError
│   ├── MaxScopeReachedError
│   ├── ScopeNotInitializedError
│   ├── ScopeSkippedError
│   ├── InvalidScopeTypeError
│   ├── ContainerClosedError
│   └── ValidationFailedError
├── ResolutionError
│   ├── ProviderNotRegisteredError
│   ├── AliasSourceNotRegisteredError
│   ├── ArgumentResolutionError
│   ├── CircularDependencyError
│   └── CreatorCallError
├── RegistrationError
│   ├── DuplicateProviderTypeError
│   ├── UnknownFactoryKwargError
│   ├── UnsupportedCreatorParameterError
│   └── InvalidScopeDependencyError
├── FinalizerError
├── AsyncFinalizerInSyncCloseError
└── GroupInstantiationError
```

## Root

- **`ModernDIError`** — base class for every error the library raises. It subclasses
  `RuntimeError` for backwards compatibility, so `except RuntimeError` keeps working. Catch
  `ModernDIError` to handle any framework error in one place.

## `ContainerError` — container and scope problems

Catch `ContainerError` for any container/scope failure.

- **`InvalidChildScopeError`** — raised when `build_child_container(scope=...)` is given a scope
  that is not deeper than the parent's (or the constructor receives a parent at an equal/shallower
  scope). The error lists the scopes that *are* allowed.
- **`MaxScopeReachedError`** — raised by `build_child_container()` with no explicit `scope` when the
  parent is already at the deepest scope (`STEP`), so there is no next level to advance to.
- **`ScopeNotInitializedError`** — raised during resolution when a provider needs a scope *deeper*
  than the current container's, and no container at that scope exists in the chain (e.g. resolving a
  `REQUEST`-scoped provider from the `APP` container). See [Troubleshooting: Scope chain](../troubleshooting/scope-chain.md).
- **`ScopeSkippedError`** — raised during resolution when the target scope is *shallower* than the
  current container but is missing from the scope chain (a level was skipped when building children).
  See [Troubleshooting: Scope chain](../troubleshooting/scope-chain.md).
- **`InvalidScopeTypeError`** — raised by the `Container` constructor when `scope` is not an
  `enum.IntEnum`.
- **`ContainerClosedError`** — raised when you resolve from, or build a child of, a container that
  has been closed (`close_sync()` / `close_async()` ran, or a `with` block exited). Re-enter the
  `with` block to reopen it.
- **`ValidationFailedError`** — raised by `Container.validate()` (and `Container(..., validate=True)`)
  when the graph has problems. Catch this for validation results; its `.errors` attribute holds the
  list of individual issues (each itself a `ResolutionError` or `RegistrationError`), and `str()`
  renders them all.

## `ResolutionError` — failures while resolving a type

Catch `ResolutionError` for any resolution failure. These carry a `dependency_path` that is
accumulated as the error propagates, so the message shows the full chain from the requested type
down to the failing dependency. `dependency_path` is a `list[ResolutionStep]`, where each
`ResolutionStep` (importable from `modern_di.exceptions`) has a `.scope` and a `.name` — inspect it
to render the chain programmatically.

- **`ProviderNotRegisteredError`** — raised by `resolve(SomeType)` when no provider is registered for
  the type. The message includes "did you mean…" suggestions when a close match exists. See
  [Troubleshooting: Missing provider](../troubleshooting/missing-provider.md).
- **`AliasSourceNotRegisteredError`** — raised when an `Alias` points at a `source_type` that has no
  registered provider (eagerly during `validate()`, or at resolution time).
- **`ArgumentResolutionError`** — raised when a creator parameter cannot be resolved: no provider
  matches its annotated type, or the parameter is unannotated. See
  [Troubleshooting: Context not set](../troubleshooting/context-not-set.md).
- **`CircularDependencyError`** — raised when the provider graph contains a cycle (A → B → A),
  detected during `validate()` or at resolution; the message shows the cycle path. See
  [Troubleshooting: Circular dependency](../troubleshooting/circular-dependency.md).
- **`CreatorCallError`** — raised when a creator's dependencies all resolved but the creator itself
  raised while being called. The original exception is preserved on `.original_error` (and as the
  `__cause__`).

## `RegistrationError` — declaration / registration problems

Catch `RegistrationError` for declaration- and registration-time problems.

- **`DuplicateProviderTypeError`** — raised when two providers are registered for the same bound type
  (within one group, across groups passed together, or against an already-registered type). See
  [Troubleshooting: Duplicate type](../troubleshooting/duplicate-type-error.md).
- **`UnknownFactoryKwargError`** — raised when `Factory(kwargs={...})` contains a key that is not a
  parameter of the creator's signature; lists the known parameters and "did you mean" hints.
- **`UnsupportedCreatorParameterError`** — raised when a creator's signature has a parameter
  `modern-di` cannot wire (e.g. an unsupported kind); names the parameter and the reason.
- **`InvalidScopeDependencyError`** — raised when a provider depends on another provider bound to a
  *deeper* scope than its own (a longer-lived provider depending on a shorter-lived one). Surfaced by
  `validate()`.

## Direct `ModernDIError` subclasses

These don't fit the register/resolve/validate grouping:

- **`FinalizerError`** — raised by `close_sync()` / `close_async()` when one or more finalizers raised
  during cleanup. The remaining finalizers still run; all errors are aggregated into this single
  exception. `.finalizer_errors` holds the list and `.is_async` records which close path ran. See
  [Lifecycle](lifecycle.md#close-failure-semantics).
- **`AsyncFinalizerInSyncCloseError`** — raised when `close_sync()` reaches a cached resource whose
  finalizer is async. Because `close_sync()` aggregates, this arrives *wrapped inside a*
  `FinalizerError` (as an entry in `.finalizer_errors`), not on its own. The cache is retained so a
  later `await close_async()` can finalize it. See [Lifecycle](lifecycle.md#close-failure-semantics).
- **`GroupInstantiationError`** — raised when a `Group` subclass is instantiated. Groups are
  namespaces and must never be created as objects.

## Security note

`modern-di` exception messages are intended for developers (logs, tracebacks during wiring). A
`CreatorCallError` embeds the wrapped exception's text, and a `FinalizerError` embeds the repr of every
finalizer exception — so if a creator or finalizer raises an error whose message contains sensitive
runtime data, that text becomes part of the `modern-di` message. The DI-specific errors themselves are
conservative (type names and provider reprs only; context values are keyed by type and never repr'd).
Applications must not echo raw exception strings to untrusted clients.
