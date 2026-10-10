# Migration guide: upgrading to modern-di 4.x

This document describes the changes required to migrate from modern-di 3.x to modern-di 4.0.

## Key changes

### `Container` takes only `scope` positionally

Every `Container` argument after `scope` is keyword-only: `Container(Scope.APP, None)` raises
`TypeError`, so pass `context=` and `groups=` by name.

### `use_lock` is removed

`Container(use_lock=...)` raises `TypeError`; drop the argument. Cached factories are always
locked, and the lock is taken only on a cache miss (see
[Design decisions](../introduction/design-decisions.md#2-cached-factories-are-thread-safe)).

### Each cached factory has its own lock

In 3.x, with the default `use_lock=True`, every cached creator ran under a shared lock: the
container's lock, or from 3.6 the lock of the whole container tree. Two cached factories that
shared the lock were never created at the same time. In 4.0 each cached factory has its own lock
in each container, so creators of different cached factories can run at the same time on
different threads. If two creators share state that is not thread-safe, guard that state with
your own lock.

On a cache miss the lock is now held while the dependencies are resolved as well. Threads that
miss together build the dependencies once, where 3.x built them once per thread and discarded all
but one. A cached creator can also wait on another thread that resolves a different cached type,
which deadlocked in 3.x.

One case that raised in 3.x can now block. If the graph has a cycle and `validate()` was never
called, two threads that cold-resolve different providers of that cycle at the same time can each
hold one lock and wait for the other forever. In 3.x both got `CircularDependencyError`. A single
thread still gets that error. Call `validate()` at startup to catch cycles before serving.

### Resolving on a closed container raises

In 3.x, resolving from a closed container, or through a child whose resolve reached a closed
ancestor, emitted `ContainerClosedWarning` and reopened it. In 4.0 the same call raises
`ContainerClosedError` and the container stays closed. `ContainerClosedWarning` is removed, so delete
any `filterwarnings` entry that names it. To use a closed container again, reopen it first with
`open()` or by re-entering `with` / `async with`, which calls `open()`. See
[Troubleshooting: ContainerClosedError](../troubleshooting/container-closed-error.md).

### Closing a root container keeps overrides

In 3.x, `close_sync()` and `close_async()` on a root container cleared every override. In 4.0 they
leave overrides in place, so an override set before a close→reopen cycle still applies after it.
If your test teardown relied on the close to clear overrides, reset them with `reset_override()` or
apply them with `with container.override(...)`. See
[Testing with overrides](../recipes/testing-overrides.md).

### Finalizers run on a closed container

In 3.x a container was marked closed only after its finalizers ran, so a finalizer could resolve from
it. That resolve could build a new instance after the original was finalized, and nothing finalized
the new one. In 4.0 the container counts as closed while its finalizers run, and a resolve from
inside a finalizer raises `ContainerClosedError`. Give the cached instance what its finalizer needs
when it is created. A finalizer that raises now also drops its cached instance, so the next resolve
after reopening builds a fresh one instead of returning the half-finalized object. See
[Close-failure semantics](../providers/lifecycle.md#close-failure-semantics).

### Scope and closed-container errors are also `ResolutionError`s

`ScopeNotInitializedError`, `ScopeSkippedError` and `ContainerClosedError` now subclass
`ResolutionError` as well as `ContainerError`, so `except ResolutionError` catches every modern-di
error raised by `resolve()` and `resolve_provider()`. `except ContainerError` still catches them. If an
`except ResolutionError` clause comes before an `except ContainerError` clause, the first one now
handles these three errors; reorder the clauses if the `ContainerError` handler should run. See
[Errors and exceptions](../providers/errors-and-exceptions.md).

### Scopes match by enum member

In 3.x a provider found its container by integer value, so a provider at a custom
`Tenancy.TENANT = 2` resolved and cached in a `Scope.SESSION` container. In 4.0 a provider resolves
only in a container built at the same enum member, and the same-valued scope of another enum raises
`ScopeSkippedError` or `ScopeNotInitializedError`. Group default scopes compare members too: two
groups that give one provider `Scope.SESSION` and `Tenancy.TENANT` raise `GroupScopeConflictError`.
A group that restamps a registered provider to another enum's member with the same value now raises
`ProviderScopeFrozenError`; 3.x accepted it silently. `validate()` reports a dependency on the
same-valued scope of another enum as `ScopeEnumMismatchError`, since it can never resolve.
Ordering is unchanged, so a child container still needs a higher integer value than its parent,
whichever enum each scope comes from. If a provider relied on the old match, give it the scope
member of the container it should resolve in. See [Custom scopes](../providers/scopes.md#custom-scopes).

### A missing context value for a required parameter raises `ContextValueNotSetError`

In 3.x, when a `Factory` parameter was backed by a `ContextProvider` and no context value was set,
a required parameter raised `ArgumentResolutionError`. In 4.0 it raises `ContextValueNotSetError`,
and the message and `.parameter_name` name the parameter. A direct resolve of the provider raises
the same error with no parameter name.

`ContextValueNotSetError` does not subclass `ArgumentResolutionError`. An
`except ArgumentResolutionError` clause that handled a missing context value in 3.x no longer
catches it; catch `ContextValueNotSetError` instead, or `ResolutionError`, which covers both.

A parameter that is nullable or has a default still falls back. With no value set, it gets its
default, or `None` for an `X | None` parameter without one. A creator that takes
`request: fastapi.Request | None = None` gets `None` when it is resolved outside a request, for
example from a FastStream consumer that shares the container. Only an argument that comes straight
from the `ContextProvider` falls back. If the parameter's provider is a `Factory` that needs the
missing value, the resolve raises.

`ContextProvider(T, default=X)` is new in 4.0. It returns `X` whenever no value is set, on a direct
resolve and for every argument it backs, and it wins over a parameter's default:

```python
tenant = providers.ContextProvider(TenantId, scope=Scope.REQUEST, default=None)
```

`ContextProvider.fetch_context_value()` is removed; resolve the provider instead, giving it a
`default=` if the value may be absent. See
[Context providers: when no value is set](../providers/context.md#when-no-value-is-set).

### The container copies `context=`

`Container(context=...)` and `build_child_container(context=...)` copy the dict you pass. In 3.x
the container kept your dict, so `set_context()` wrote into it, and two containers built from the
same dict saw each other's values. A module-level dict reused for every request leaked values set on
one request into the next. In 4.0 `set_context()` changes only that container, and changes you make
to your dict after building the container are not seen by it. Call `set_context()` on the container
to add a value later.

### Exception attributes are renamed

`ArgumentResolutionError` names the creator parameter the same way the other errors do:

- `.arg_name` is now `.parameter_name`, and `.arg_type` is now `.parameter_type`. The constructor
  keywords are renamed to match.
- `.bound_type` holds only the provider's bound type, and is `None` when the provider has none. In
  3.x it held the creator in that case; read `.creator` for it now.
- `.member_types` is stored: the union members when the parameter has no single type.
- The constructor requires `creator=`, the creator whose parameter could not be wired. Code that
  builds the error itself, in a test for example, must pass it.

`ContextValueNotSetError` stores `.provider_scope`, the provider's scope as an `IntEnum`, and
`.parameter_name`. Neither attribute existed in 3.x, so code that only catches the error or reads
`.context_type` is unaffected. Code that constructs it must pass `provider_scope=Scope.APP` (or
another member) in place of the 3.x `scope_name="APP"` string.

`DependencyPathMixin` is removed and `ResolutionError` carries `dependency_path` itself, so a 3.x
`isinstance(e, DependencyPathMixin)` check becomes `isinstance(e, ResolutionError)`.
`modern_di.exceptions` no longer re-exports `SUGGESTION_HEADER`; import it from
`modern_di.exceptions.rendering` if you still need it.

### `FinalizerError` is an `ExceptionGroup`

`FinalizerError` now subclasses `ExceptionGroup` as well as `ModernDIError`, so `except*` can catch
the finalizer errors inside it by type, `AsyncFinalizerInSyncCloseError` included.

- `.finalizer_errors` is removed. Read `.exceptions`, which is a tuple where `.finalizer_errors`
  was a list.
- The constructor keyword `finalizer_errors=` is now `exceptions=`.
- `.is_async` is unchanged, and a group that `except*` splits off keeps it.
- `except FinalizerError` and `except ModernDIError` still catch it.
- Its message is one line naming each kind of error with its count, such as
  `Container.close_sync() found 1 finalizer error(s): ValueError (1)`, where 3.x listed every
  finalizer exception. Each finalizer exception carries a note naming the type of the cached
  instance whose finalizer raised it.

```python
# 3.x
try:
    container.close_sync()
except exceptions.FinalizerError as exc:
    errors = exc.finalizer_errors

# 4.0
try:
    container.close_sync()
except exceptions.FinalizerError as exc:
    errors = exc.exceptions

# 4.0, by type
try:
    container.close_sync()
except* exceptions.AsyncFinalizerInSyncCloseError:
    ...
```

### `ValidationFailedError` is an `ExceptionGroup`

`ValidationFailedError` now subclasses `ExceptionGroup` as well as `ContainerError`, so `except*`
can catch the issues inside it by type.

- `.errors` is removed. Read `.exceptions`, which is a tuple where `.errors` was a list.
- The constructor keyword `errors=` is now `exceptions=`.
- `except ValidationFailedError`, `except ContainerError` and `except ModernDIError` still catch it.
- `str()` is one line naming each kind of issue with its count, such as
  `Container.validate() found 3 issue(s): ArgumentResolutionError (2), CircularDependencyError (1)`,
  plus the troubleshooting link. In 3.x it held every issue's full message. A traceback, or
  `logger.exception`, now shows each issue in full below that line. To get the messages yourself,
  read `str(error)` for each `error` in `.exceptions`.

```python
# 3.x
try:
    container.validate()
except exceptions.ValidationFailedError as exc:
    errors = exc.errors

# 4.0
try:
    container.validate()
except exceptions.ValidationFailedError as exc:
    errors = exc.exceptions

# 4.0, by type
try:
    container.validate()
except* exceptions.ArgumentResolutionError:
    ...
```

### More exception attributes are renamed

- `ChildContainerRegistrationError.scope` is now `.container_scope`, the name every other error
  uses for a container's scope. The constructor keyword is renamed to match.
- `AsyncFinalizerInSyncCloseError.finalizer_type` is now `.instance_type`, the type of the cached
  instance whose finalizer is async. The constructor keyword is renamed to match.
- `InvalidChildScopeError.allowed_scopes` holds scope enum members where it held their names. Read
  `[scope.name for scope in exc.allowed_scopes]` for the 3.x list. The message is unchanged.
- `InvalidScopeDependencyError.dep_chain`, `.dep_provider` and `.dep_terminal` are now
  `.dependency_chain`, `.dependency_provider` and `.dependency_terminal`. The constructor keyword
  `dep_chain=` is now `dependency_chain=`.
- `ProviderScopeFrozenError.provider_name` and `GroupScopeConflictError.provider_name` are replaced
  by `.provider`, the provider object, as on `InvalidScopeDependencyError`. Read
  `exc.provider.display_name` for the 3.x string. The constructors take `provider=` in place of
  `provider_name=`, and the messages are unchanged.
- `ProviderNotRegisteredError.provider_type` is now `.dependency_type`, the type that was
  requested, named like the argument of `resolve()` and `find_provider()`. The constructor keyword
  is renamed to match. `DuplicateProviderTypeError.provider_type` keeps its name, since it holds a
  bound type. The message now reads `No provider is registered for MissingDep.` where 3.x printed
  `Provider of type <class 'myapp.MissingDep'> is not registered in providers registry.`, so update
  any test that matched the old text.

### `ScopeSkippedError` names the root of the chain

`ScopeSkippedError` stores `.root_scope`, the scope of the root container of the chain it was raised
in, and its message names that root. In 3.x the message said the chain started at the resolving
container's scope, which was wrong whenever that container was a child. Code that constructs the
error must pass `root_scope=`.

### `Factory(cache=)` takes only a bool or a `CacheSettings`

`cache=None` raises `TypeError`, and so does any other value that is not `True`, `False` or a
`CacheSettings`. Replace `cache=None` with `cache=False`, or drop the argument: an uncached
factory is still the default.

### Provider internals are no longer public

These methods were never documented and no integration calls them. In 4.0 they are private, so
code that calls them raises `AttributeError`:

- `AbstractProvider.get_dependencies()`, `AbstractProvider.redirect_target()` and
  `AbstractProvider.iter_validation_issues()`. Call `container.validate()` to check the graph.
- `Factory.wiring_plan()`, `Factory.can_call_positionally()` and `Factory.resolution_step()`.
- `Alias.find_source()`. Resolve the alias instead.
- `CacheSettings.coerce()`. Pass `True`, `False` or a `CacheSettings` to `Factory(cache=)`.

### `AbstractProvider` is a plain class

`AbstractProvider` no longer derives from `abc.ABC`. It never declared an abstract method, and the
provider set is closed. Only code that relied on `ABCMeta` is affected:
`AbstractProvider.register(...)` raises `AttributeError`. `isinstance(x, AbstractProvider)` works
as before for every provider, and type hints that name `AbstractProvider` need no change.

### `NewType` and type alias annotations are wired

In 3.x a parameter annotated with a `NewType` or a `type X = ...` alias was treated as unannotated,
and a creator returning one got no bound type. In 4.0 both are bound types of their own: the
parameter resolves from the provider declared with `bound_type=UserId`, and `Factory(make_user_id)`
with `-> UserId` registers under `UserId`. If a group already has a provider bound to the same
`NewType` or alias, registration now raises `DuplicateProviderTypeError`; pass `bound_type=None`
to the one that should stay unregistered.

Classes whose signature comes from `__new__`, such as `NamedTuple` subclasses, now wire their
parameters from the `__new__` annotations.

A `Factory` whose creator returns a union of several types (`-> A | B`) still gets no bound type,
and now emits a `UserWarning` saying so. Pass `bound_type=` explicitly to silence it.

### `Container` registries are private

`providers_registry`, `cache_registry`, `context_registry` and `overrides_registry` are no longer
public attributes of `Container`. To look up the provider registered for a type, call
`container.find_provider(SomeType)`, which returns the provider or `None`:

```python
# 3.x
provider = container.providers_registry.find_provider(SomeType)

# 4.0
provider = container.find_provider(SomeType)
```

Register providers with `groups=` on the root or with `add_providers()`, and manage overrides with
`override()` and `reset_override()`. See
[Container: looking up a provider](../providers/container.md#looking-up-a-provider).

### Only four modules are public

Import public names from `modern_di`, `modern_di.providers`, `modern_di.exceptions` and
`modern_di.integrations`, and from no other module. Every other module is internal and can change in
any release. 4.0 already changes several:

- `modern_di.registries.cache_registry` and `modern_di.registries.context_registry` are deleted. A
  container keeps its cache and context itself. An import from either path raises
  `ModuleNotFoundError`.
- `modern_di.scope` holds only `Scope`. The private helpers it held next to it in 3.x are removed.
  Import `Scope` from `modern_di`.
- `modern_di.types.P`, an unused `ParamSpec`, is removed.

See [What is public](../providers/advanced-api.md#what-is-public).

### `Container.closed` is read-only

`container.closed` still reports whether the container is closed, but assigning to it raises
`AttributeError`. Close a container with `close_sync()`, `close_async()` or by leaving `with` /
`async with`, and reopen it with `open()`.

### `Container(...)` builds roots only

The `parent_container=` argument is removed, and passing it raises `TypeError`. Build a child with
`build_child_container()`:

```python
# 3.x
request_container = Container(scope=Scope.REQUEST, parent_container=app_container, context=context)

# 4.0
request_container = app_container.build_child_container(scope=Scope.REQUEST, context=context)
```

In 3.x a child built that way could also take `groups=`, which registered them into the registry
the whole tree shares. Pass the groups to the root container instead. `add_providers()` on a child
still raises `ChildContainerRegistrationError`, and its message changed, so update any test that
matched the old `Container.add_providers can only be called on a root container` text.

`build_child_container()` on a `Container` subclass still returns an instance of that subclass, but
it no longer calls the subclass's `__init__`. If your subclass sets state in `__init__`, that state
now exists on the root only.

### `Container.scope` and `Container.parent_container` are read-only

Assigning to either raises `AttributeError`. In 3.x reassigning `scope` broke scope lookups from the
container's children.

### Provider attributes are read-only

Assigning to `bound_type` or `provider_id` on any provider, `cache_settings` on a `Factory`, or
`context_type` or `default` on a `ContextProvider` raises `AttributeError`. Changing them after
registration was never supported, because the container keeps what it read when it registered and
compiled the provider. Declare a new provider instead.

`CacheSettings` is frozen: assigning to `clear_cache` or `finalizer` raises
`dataclasses.FrozenInstanceError`. Build a new `CacheSettings` instead.

### Typing changes

- `ContextProvider(T, default=None)` is typed `ContextProvider[T | None]`, so `resolve_provider()`
  on it returns `T | None`. In 3.x it was typed `ContextProvider[T]` while resolving to `None`.
  Without `default=`, or with a default of type `T`, it stays `ContextProvider[T]`.
- `CacheSettings` is contravariant in its type parameter, the type its finalizer accepts. A
  finalizer that takes a subclass of what the creator returns, as in
  `Factory(make_base, cache=CacheSettings(finalizer=close_sub))`, is now a type error. In 3.x it
  type-checked and failed at close with `AttributeError`. Make the finalizer accept the creator's
  return type or a base of it.

### Internal helpers on providers, settings and errors are private

None of these were meant for use outside the package. Accessing them raises `AttributeError`:

- `AbstractProvider.mark_registered()`. Registering a provider through a container does it.
- `CacheSettings.is_async_finalizer`. The advanced API page listed it as an extension point, but
  `close_async()` never read it.
- `ResolutionError.prepend_step()`.
- `ContextValueNotSetError.name_parameter()`.
- `CreatorCallError.from_type_error()`.

### A closed container raises before the provider lookup

`resolve()` on a closed container raises `ContainerClosedError` even when the type is not
registered. In 3.x that call raised `ProviderNotRegisteredError`.

### `Alias` requires `bound_type`

In 3.x `bound_type` defaulted to `source_type`, so `Alias(X)` registered under `X` and resolved to
itself: `validate()` reported a `CircularDependencyError`, or registration raised
`DuplicateProviderTypeError` when a provider for `X` existed too. In 4.x `bound_type` has no
default. `Alias(X)` raises `TypeError`, and `Alias(X, bound_type=X)` raises
`AliasBoundToSourceError`. Pass the type the alias answers for, or `bound_type=None` to use it
by reference only:

```python
# 3.x
alias = providers.Alias(PostgresDatabase)

# 4.x
alias = providers.Alias(PostgresDatabase, bound_type=DatabaseProtocol)
```

### The 3.x deprecations are removed

- `Container(validate=...)` raises `TypeError`, and `ValidateArgumentWarning` is gone with it. Drop
  the argument and call `container.validate()` where you want the graph checked.
- `Container.scope_map` and `Container.lock` are removed. Nothing replaces them as public API; call
  `find_container(scope)` to reach an ancestor.
- `ContextValueNoneWarning` and `UnvalidatedContainerWarning` are removed. Neither has been emitted
  since 3.0, so delete any `filterwarnings` entry or import that names them.
- The `modern_di.exceptions.warnings` module held only these three warnings and is deleted. An
  import from that path raises `ModuleNotFoundError`, so delete it.
