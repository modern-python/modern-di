# Errors and exceptions

Every exception `modern-di` raises lives in `modern_di.exceptions` and descends from one root,
`ModernDIError`, which subclasses `RuntimeError` (see
[Design decisions](../introduction/design-decisions.md#7-errors-are-runtimeerrors)). The hierarchy
groups errors by when they happen: registering providers, validating the graph, resolving a type, or
closing a container. Each concrete error has a troubleshooting page with its cause and fix, and its
printed message ends with a `See:` line linking to that page.

The class hierarchy and each error's attributes (`.dependency_type`, `.cycle_path`, `.suggestions`,
`.dependency_path`, ...) are the contract. The message text is diagnostic output and may change in
any release, so read an attribute instead of parsing the message.

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
│   ├── AliasBoundToSourceError
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

## Catching errors

Catch `ModernDIError` to handle any error from the library in one place, or a category base to
handle one group. `ScopeNotInitializedError`, `ScopeSkippedError` and `ContainerClosedError` are both
a `ContainerError` and a `ResolutionError`, so either `except` catches them:

```python
from modern_di import Container, Group, Scope, exceptions, providers


class Session: ...


class Dependencies(Group):
    session = providers.Factory(Session, scope=Scope.REQUEST)


container = Container(groups=[Dependencies])

try:
    container.resolve(Session)  # no REQUEST container in this chain
except exceptions.ResolutionError as exc:
    print(type(exc).__name__, isinstance(exc, exceptions.ContainerError))
    print(exc.provider_scope.name, exc.container_scope.name)
```

`ValidationFailedError` and `FinalizerError` are also `ExceptionGroup`s, so `except*` picks out the
entries of one kind. What it does not catch is raised again as the same class, holding only the
remaining entries:

```python
class Missing: ...


class NeedsMissing:
    def __init__(self, missing: Missing) -> None:
        self.missing = missing


class Unresolvable(Group):
    needs_missing = providers.Factory(NeedsMissing)


try:
    Container(groups=[Unresolvable]).validate()
except* exceptions.ArgumentResolutionError as group:
    for error in group.exceptions:
        print("unresolvable parameter:", error.parameter_name)
```

## Where each error comes from

Each table row names what raises the error and the attributes to read. The linked page has the
printed message, the cause and the fix.

### `ContainerError`: building containers and validating

| Error | Raised by | Inspect |
|---|---|---|
| [`InvalidChildScopeError`](../troubleshooting/invalid-child-scope-error.md) | `build_child_container(scope=...)` with a scope that is not deeper than the parent's | `.parent_scope`, `.child_scope`, `.allowed_scopes` |
| [`MaxScopeReachedError`](../troubleshooting/max-scope-reached-error.md) | `build_child_container()` without `scope=` when the parent's enum has no deeper member | `.parent_scope` |
| [`InvalidScopeTypeError`](../troubleshooting/invalid-scope-type-error.md) | `Container(scope=...)`, `build_child_container(scope=...)` or `class G(Group, scope=...)` with a value that is not an `IntEnum` member | `.scope_value` |
| [`ValidationFailedError`](../troubleshooting/validation-failed-error.md) | `Container.validate()`, which is the only thing that validates | `.exceptions` |

The three errors that are also a `ResolutionError` are in the next table.

### `ResolutionError`: resolving a type

| Error | Raised by | Inspect |
|---|---|---|
| [`ScopeNotInitializedError`](../troubleshooting/scope-not-initialized-error.md) | a resolve that needs a scope deeper than every container in the chain | `.provider_scope`, `.container_scope` |
| [`ScopeSkippedError`](../troubleshooting/scope-skipped-error.md) | a resolve that needs a shallower scope with no container in the chain | `.provider_scope`, `.container_scope`, `.root_scope` |
| [`ContainerClosedError`](../troubleshooting/container-closed-error.md) | a resolve that reaches a closed container | `.container_scope` |
| [`ProviderNotRegisteredError`](../troubleshooting/missing-provider.md) | `resolve(SomeType)` when no provider is registered for the type | `.dependency_type`, `.suggestions` |
| [`AliasSourceNotRegisteredError`](../troubleshooting/alias-source-not-registered-error.md) | `validate()` or a resolve, for an `Alias` whose source type has no provider | `.source_type` |
| [`ArgumentResolutionError`](../troubleshooting/argument-resolution-error.md) | `validate()` or a resolve, for a creator parameter with no matching provider or no annotation | `.parameter_name`, `.parameter_type`, `.member_types`, `.bound_type`, `.creator`, `.suggestions` |
| [`CircularDependencyError`](../troubleshooting/circular-dependency.md) | `validate()`, or the runtime guard in a resolve, for a cycle in the graph | `.steps`, `.cycle_path`, `.cycle_locations` |
| [`CreatorCallError`](../troubleshooting/creator-call-error.md) | a resolve whose arguments do not bind to the creator's signature, typically a `kwargs` or `skip_creator_parsing` mismatch | `.creator`, `.original_error` |
| [`ContextValueNotSetError`](../troubleshooting/context-not-set.md) | a resolve of a `ContextProvider` with no value set and no `default=`, directly or for a required parameter | `.context_type`, `.provider_scope`, `.parameter_name` |

Every `ResolutionError` also has `.dependency_path`, a list of `ResolutionStep` objects (importable
from `modern_di.exceptions`), each with a `.scope`, a `.name` and a `.location`. A resolve fills it in
as the error propagates, from the type you asked for down to the one that failed. While it is
non-empty, the message starts with `Cannot resolve dependency chain:`, draws one line per step, and
ends the chain with a `caused by:` line holding the error's own message. `ContainerClosedError`
always has an empty path, and `CircularDependencyError` draws its cycle from `.steps` instead.

### `RegistrationError`: declaring and registering providers

| Error | Raised by | Inspect |
|---|---|---|
| [`DuplicateProviderTypeError`](../troubleshooting/duplicate-type-error.md) | registering two providers for the same bound type | `.provider_type`, `.first_provider`, `.second_provider` |
| [`AliasBoundToSourceError`](../troubleshooting/alias-bound-to-source-error.md) | declaring an `Alias` whose `bound_type` is its `source_type` | `.source_type` |
| [`ChildContainerRegistrationError`](../troubleshooting/child-container-registration-error.md) | `add_providers()` on a child container | `.container_scope` |
| [`GroupScopeConflictError`](../troubleshooting/group-scope-conflict-error.md) | sharing a provider with no `scope=` between two groups declared with different `scope=` | `.provider`, `.first_group`, `.first_scope`, `.second_group`, `.second_scope` |
| [`ProviderScopeFrozenError`](../troubleshooting/provider-scope-frozen-error.md) | a `Group` that would change the scope of a provider already registered with a container | `.provider`, `.group_name`, `.current_scope`, `.new_scope` |
| [`UnknownFactoryKwargError`](../troubleshooting/unknown-factory-kwarg-error.md) | `Factory(kwargs={...})` with a key that is not a parameter of the creator | `.creator`, `.unknown_keys`, `.known_keys`, `.suggestions` |
| [`UnsupportedCreatorParameterError`](../troubleshooting/unsupported-creator-parameter-error.md) | a creator parameter `modern-di` cannot wire | `.creator`, `.parameter_name`, `.reason` |
| [`InvalidScopeDependencyError`](../troubleshooting/scope-chain.md) | `validate()`, for a provider that depends on a deeper-scoped one | `.provider`, `.parameter_name`, `.dependency_chain`, `.dependency_provider`, `.dependency_terminal` |
| [`ScopeEnumMismatchError`](../troubleshooting/scope-enum-mismatch-error.md) | `validate()`, for a dependency at a same-valued scope of another enum | `.provider`, `.parameter_name`, `.dependency_chain`, `.dependency_provider`, `.dependency_terminal` |

### Direct `ModernDIError` subclasses

| Error | Raised by | Inspect |
|---|---|---|
| [`FinalizerError`](../troubleshooting/finalizer-error.md) | `close_sync()` or `close_async()` after one or more finalizers raised | `.exceptions`, `.is_async` |
| [`AsyncFinalizerInSyncCloseError`](../troubleshooting/async-finalizer-in-sync-close-error.md) | `close_sync()` reaching an async finalizer; it arrives as an entry inside a `FinalizerError` | `.instance_type` |
| [`GroupInstantiationError`](../troubleshooting/group-instantiation-error.md) | instantiating a `Group` subclass | `.group_name` |

For `ValidationFailedError` and `FinalizerError`, `str()` is two lines: a summary naming each kind of
entry with its count, then the `See:` line. A traceback, or `logger.exception`, prints every entry in
full below it.

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

## Security note

`modern-di` messages are written for developers reading logs and tracebacks. The errors about the
graph name types, parameters, scopes and providers. A context value never appears in a message,
because context is keyed by type. Two errors can carry your runtime data:

- `InvalidScopeTypeError` shows the `repr()` of the value passed as `scope=`.
- `FinalizerError` holds the exceptions your finalizers raised, and a traceback prints each one with
  its message.

An exception raised inside a creator's body propagates unchanged, with whatever message your code
gave it. Do not echo raw exception strings to untrusted clients.
