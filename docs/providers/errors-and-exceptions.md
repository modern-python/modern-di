# Errors and exceptions

Every exception `modern-di` raises lives in `modern_di.exceptions` and descends from a single
root, `ModernDIError`. The hierarchy is grouped by *when* the failure happens (registering
providers, validating the graph, resolving a type, or closing a container), so you can catch a
whole category with one `except`.

The class hierarchy and each error's structured attributes (`.provider_type`, `.cycle_path`,
`.suggestions`, `.dependency_path`, ...) are the contract. The rendered message text is diagnostic
output and may change in any release; read an attribute, never parse the message.

```python
from modern_di import exceptions
```

## Pickling and copying

Every exception can be pickled and copied, so it can cross a process pool or a task queue. The
unpickled error has the same class, `str()` and `args`, and keeps each attribute whose value
pickles. An attribute that does not, such as a lambda `creator` or a class defined inside a
function, comes back as its `repr()` string. A `FinalizerError` entry that does not pickle comes
back as a `RuntimeError` holding its `repr()`. As with any Python exception, `__cause__` and the
traceback are dropped.

The check that decides whether an attribute pickles runs in the process that pickles the error. A
value that only loads there can still fail to load in another process. A class defined in
`__main__` is the common case: the receiving process has a different `__main__`.

## Hierarchy

```
ModernDIError (RuntimeError)
├── ContainerError
│   ├── InvalidChildScopeError
│   ├── MaxScopeReachedError
│   ├── InvalidScopeTypeError
│   ├── ValidationFailedError (also an ExceptionGroup)
│   ├── ScopeNotInitializedError (also a ResolutionError)
│   ├── ScopeSkippedError (also a ResolutionError)
│   └── ContainerClosedError (also a ResolutionError)
├── ResolutionError
│   ├── ScopeNotInitializedError (also a ContainerError)
│   ├── ScopeSkippedError (also a ContainerError)
│   ├── ContainerClosedError (also a ContainerError)
│   ├── ProviderNotRegisteredError
│   ├── AliasSourceNotRegisteredError
│   ├── ArgumentResolutionError
│   ├── CircularDependencyError
│   ├── CreatorCallError
│   └── ContextValueNotSetError
├── RegistrationError
│   ├── DuplicateProviderTypeError
│   ├── ChildContainerRegistrationError
│   ├── GroupScopeConflictError
│   ├── ProviderScopeFrozenError
│   ├── UnknownFactoryKwargError
│   ├── UnsupportedCreatorParameterError
│   ├── InvalidScopeDependencyError
│   └── ScopeEnumMismatchError
├── FinalizerError (also an ExceptionGroup)
├── AsyncFinalizerInSyncCloseError
└── GroupInstantiationError
```

## Root

- `ModernDIError` is the base class for every error the library raises. It subclasses
  `RuntimeError`, so `except RuntimeError` catches it too (see
  [Design decisions](../introduction/design-decisions.md#7-errors-are-runtimeerrors)). Catch
  `ModernDIError` to handle any framework error in one place.

## `ContainerError`: container and scope problems

Catch `ContainerError` for any container/scope failure. `ScopeNotInitializedError`,
`ScopeSkippedError` and `ContainerClosedError` are both a `ContainerError` and a `ResolutionError`,
so either `except` catches them; they are described under `ResolutionError` below.

- `InvalidChildScopeError` is raised when `build_child_container(scope=...)` is given a scope
  that is not deeper than the parent's (or the constructor receives a parent at an equal/shallower
  scope). The error lists the scopes that *are* allowed. See
  [Troubleshooting: InvalidChildScopeError](../troubleshooting/invalid-child-scope-error.md).
- `MaxScopeReachedError` is raised by `build_child_container()` with no explicit `scope` when the
  parent is already at the deepest scope (`STEP`), so there is no next level to advance to. See
  [Troubleshooting: MaxScopeReachedError](../troubleshooting/max-scope-reached-error.md).
- `InvalidScopeTypeError` is raised by the `Container` constructor, by `build_child_container()`,
  and by a `Group` subclass declared as `class G(Group, scope=...)`, when `scope` is not an
  `enum.IntEnum`. See
  [Troubleshooting: InvalidScopeTypeError](../troubleshooting/invalid-scope-type-error.md).
- `ValidationFailedError` is raised only by `Container.validate()`. Catch this for validation
  results. It is an `ExceptionGroup`: `.exceptions` holds the individual issues (each itself a
  `ResolutionError` or `RegistrationError`), and `except*` catches them by type. `str()` is one
  line with the count of each kind; a traceback shows every issue in full below it.
  Nothing validates automatically (not construction, not `open()`, not `add_providers`, not
  `resolve()`), so call `validate()` explicitly whenever you want the whole graph checked; an
  integration that registers its own providers after construction (via `add_providers`) should call
  it after that registration. See
  [Lifecycle: validation](lifecycle.md#validation),
  [Migration: To 3.x](../migration/to-3.x.md) and
  [Troubleshooting: ValidationFailedError](../troubleshooting/validation-failed-error.md).

## `ResolutionError`: failures while resolving a type

Catch `ResolutionError` for any resolution failure. These carry a `dependency_path` that is
accumulated as the error propagates, so the message shows the full chain from the requested type
down to the failing dependency. `dependency_path` is a `list[ResolutionStep]`, where each
`ResolutionStep` (importable from `modern_di.exceptions`) has a `.scope` and a `.name`; inspect it
to render the chain programmatically.

- `ScopeNotInitializedError` is raised during resolution when a provider needs a scope *deeper*
  than the current container's, and no container at that scope exists in the chain (e.g. resolving a
  `REQUEST`-scoped provider from the `APP` container). For a runtime *captive dependency* (a
  shallower-scoped provider depending, directly or transitively, on this deeper-scoped one), its
  `dependency_path` names both the capturing provider and the one that failed. See
  [Troubleshooting: ScopeNotInitializedError](../troubleshooting/scope-not-initialized-error.md).
- `ScopeSkippedError` is raised during resolution when the target scope is *shallower* than the
  current container but is missing from the scope chain (a level was skipped when building children).
  See [Troubleshooting: ScopeSkippedError](../troubleshooting/scope-skipped-error.md).
- `ContainerClosedError` is raised by `resolve()` / `resolve_provider()` when the call reaches a
  closed container: the one you called, or an ancestor whose scope a child's resolve reaches back
  into. Its `.container_scope` names the closed one, and its `dependency_path` is always empty. A
  container is open from construction and is closed by `close_sync()`, `close_async()`, or leaving
  `with` / `async with`. It stays closed until you call `container.open()` or enter it again with
  `with` / `async with`, which calls `open()`.
  `build_child_container()` never checks or touches any container's open/closed state, so building
  a child of a closed parent does not raise by itself. See
  [Lifecycle: closing and reopening](lifecycle.md#closing-and-reopening) and
  [Troubleshooting: ContainerClosedError](../troubleshooting/container-closed-error.md).
- `ProviderNotRegisteredError` is raised by `resolve(SomeType)` when no provider is registered for
  the type. The message includes "did you mean…" suggestions when a close match exists. See
  [Troubleshooting: Missing provider](../troubleshooting/missing-provider.md).
- `AliasSourceNotRegisteredError` is raised when an `Alias` points at a `source_type` that has no
  registered provider (eagerly during `validate()`, or at resolution time). See
  [Troubleshooting: AliasSourceNotRegisteredError](../troubleshooting/alias-source-not-registered-error.md).
- `ArgumentResolutionError` is raised when a creator parameter cannot be resolved: no provider
  matches its annotated type, or the parameter is unannotated. Inspect `.parameter_name`,
  `.parameter_type` (or `.member_types` for a union), `.bound_type`, and `.creator`. See
  [Troubleshooting: ArgumentResolutionError](../troubleshooting/argument-resolution-error.md).
- `CircularDependencyError` is raised when the provider graph contains a cycle (A → B → A); the
  message shows the cycle path. Raised eagerly by `validate()`, and also by a bare `resolve()` on an
  unvalidated cyclic graph via a runtime guard. The guard covers one thread resolving: concurrent
  first resolves of an unvalidated cyclic graph can block instead, so call `validate()` at startup. See
  [Troubleshooting: Circular dependency](../troubleshooting/circular-dependency.md#the-runtime-cycle-guard-without-validate).
- `CreatorCallError` is raised when a creator's dependencies all resolved but argument binding
  failed while calling it (the assembled arguments don't match the signature, typically a `kwargs` /
  `skip_creator_parsing` mismatch). Exceptions raised *inside* the creator body are never wrapped.
  Most propagate unchanged; a `ResolutionError` from a `container.resolve()` call in the body gains
  the creator's step in its chain. The binding `TypeError` is preserved on `.original_error` (and as the `__cause__`).
  See [Troubleshooting: CreatorCallError](../troubleshooting/creator-call-error.md).
- `ContextValueNotSetError` is raised when a `ContextProvider` with no `default=` is resolved and
  no value is set, either directly (`container.resolve(SomeContextType)`) or as the argument for a
  required `Factory` parameter. A parameter that is nullable or has a default gets that default, or
  `None`, instead. See
  [Migration: To 4.x](../migration/to-4.x.md#a-missing-context-value-for-a-required-parameter-raises-contextvaluenotseterror).
  Inspect `.context_type`, `.provider_scope`, and `.parameter_name` (the parameter, or `None` for a
  direct resolve). See
  [Troubleshooting: Context not set](../troubleshooting/context-not-set.md).

## `RegistrationError`: declaration / registration problems

Catch `RegistrationError` for declaration mistakes. Each is detected when the provider or group is
declared or registered, or by `validate()`, which reports `InvalidScopeDependencyError` and
`ScopeEnumMismatchError`.

- `DuplicateProviderTypeError` is raised when two providers are registered for the same bound type
  (within one group, across groups passed together, or against an already-registered type). See
  [Troubleshooting: Duplicate type](../troubleshooting/duplicate-type-error.md).
- `ChildContainerRegistrationError` is raised by `Container.add_providers()` when called on a child
  container. Registration is root-only because the providers registry is shared tree-wide, so
  registering from a child would mutate every container in the tree. Call `add_providers` on the root
  container instead. Inspect `.container_scope` for the offending child container's scope. See
  [Container: registering after construction](container.md#registering-providers-after-construction) and
  [Troubleshooting: ChildContainerRegistrationError](../troubleshooting/child-container-registration-error.md).
- `GroupScopeConflictError` is raised when a scope-defaulted provider (no explicit `scope=`) is
  shared by two `Group` subclasses declared with different `scope=` kwargs; the provider's scope
  cannot follow both defaults at once, and import order must never be what decides it. Inspect
  `.provider`, `.first_group`/`.first_scope`, and `.second_group`/`.second_scope`. See
  [Troubleshooting: GroupScopeConflictError](../troubleshooting/group-scope-conflict-error.md).
- `ProviderScopeFrozenError` is raised when a `Group` would change the scope of a provider that
  is already registered with a container. Resolvers compiled before the change captured the old
  scope, so applying it would make the same provider resolve differently through an existing
  container than through a fresh one. Inspect `.provider`, `.group_name`, `.current_scope`,
  `.new_scope`. See
  [Troubleshooting: ProviderScopeFrozenError](../troubleshooting/provider-scope-frozen-error.md).
- `UnknownFactoryKwargError` is raised when `Factory(kwargs={...})` contains a key that is not a
  parameter of the creator's signature; lists the known parameters and "did you mean" hints. See
  [Troubleshooting: UnknownFactoryKwargError](../troubleshooting/unknown-factory-kwarg-error.md).
- `UnsupportedCreatorParameterError` is raised when a creator's signature has a parameter
  `modern-di` cannot wire (e.g. an unsupported kind); names the parameter and the reason. See
  [Troubleshooting: UnsupportedCreatorParameterError](../troubleshooting/unsupported-creator-parameter-error.md).
- `InvalidScopeDependencyError` is raised when a provider depends on another provider bound to a
  *deeper* scope than its own (a longer-lived provider depending on a shorter-lived one). Surfaced by
  `validate()`. Renders the chain from the depender to the provider that supplies the dependency;
  `.dependency_chain` carries that chain, with `.dependency_provider` and `.dependency_terminal` as
  its ends. See
  [Troubleshooting: Scope chain](../troubleshooting/scope-chain.md).
- `ScopeEnumMismatchError` is raised when a provider depends on another provider whose scope has
  the same integer value but comes from a different enum, such as `Scope.SESSION` and a custom
  `Tenancy.TENANT = 2`. Each child container's value is higher than its parent's, so the two scopes
  can never be in one container chain. Surfaced by `validate()`. Inspect `.provider`,
  `.parameter_name` and `.dependency_chain`, with `.dependency_provider` and `.dependency_terminal`
  as its ends. See
  [Troubleshooting: ScopeEnumMismatchError](../troubleshooting/scope-enum-mismatch-error.md).

## Direct `ModernDIError` subclasses

These don't fit the register/resolve/validate grouping:

- `FinalizerError` is raised by `close_sync()` / `close_async()` when one or more finalizers raised
  during cleanup. The remaining finalizers still run; all errors are aggregated into this single
  exception. It is also an `ExceptionGroup`, so `except*` can catch the finalizer errors by type.
  `.exceptions` holds them as a tuple and `.is_async` records which close path ran. See
  [Lifecycle](lifecycle.md#close-failure-semantics) and
  [Troubleshooting: FinalizerError](../troubleshooting/finalizer-error.md).
- `AsyncFinalizerInSyncCloseError` is raised when `close_sync()` reaches a cached resource whose
  finalizer is async. Because `close_sync()` aggregates, this arrives inside a `FinalizerError` (as
  an entry in `.exceptions`), so catch it with `except* AsyncFinalizerInSyncCloseError`. The cache is retained so a
  later `await close_async()` can finalize it. See [Lifecycle](lifecycle.md#close-failure-semantics) and
  [Troubleshooting: AsyncFinalizerInSyncCloseError](../troubleshooting/async-finalizer-in-sync-close-error.md).
- `GroupInstantiationError` is raised when a `Group` subclass is instantiated. Groups are
  namespaces and must never be created as objects. See
  [Troubleshooting: GroupInstantiationError](../troubleshooting/group-instantiation-error.md).

## Security note

`modern-di` exception messages are intended for developers (logs, tracebacks during wiring). A
`CreatorCallError` embeds the wrapped exception's text, and a `FinalizerError` embeds the repr of every
finalizer exception. So if a creator or finalizer raises an error whose message contains sensitive
runtime data, that text becomes part of the `modern-di` message. The DI-specific errors themselves are
conservative (type names and provider reprs only; context values are keyed by type and never repr'd).
Applications must not echo raw exception strings to untrusted clients.
