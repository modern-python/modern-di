# Container Provider

The Container Provider is a special provider that you should not initialize.
It is automatically registered with each container, so you can resolve the container itself directly.

## Injecting the Container Itself

You can inject the container into your dependencies in two ways:

### Automatic Injection (Type-Based)

If your creator function has a parameter annotated with `Container`, it will be automatically resolved:

```python
from modern_di import Container, Group, Scope, providers

def my_creator(di_container: Container) -> str:
    # Access the container's scope or other properties
    return f"Container scope: {di_container.scope.name}"

class Dependencies(Group):
    my_factory = providers.Factory(scope=Scope.APP, creator=my_creator)

container = Container(groups=[Dependencies])
result = container.resolve(str)
# result: "Container scope: APP"
```

### Explicit Injection

You can also explicitly inject the container using `providers.container_provider`:

```python
from modern_di import Container, Group, Scope, providers

def another_creator(di_container: Container) -> str:
    # Use the container to manually resolve dependencies
    return "some value"

class Dependencies(Group):
    another_factory = providers.Factory(
        scope=Scope.APP,
        creator=another_creator,
        kwargs={"di_container": providers.container_provider}
    )
```

## Which container you get

Resolving `Container` returns the **calling container** — the deepest, most-specific container in
the active chain, not the `APP` root. The `container_provider` simply hands back whichever container
ran the resolve, so a `REQUEST` child resolves `Container` to *itself*:

```python
app_container = Container(scope=Scope.APP)
request_container = app_container.build_child_container(scope=Scope.REQUEST)

assert app_container.resolve(Container) is app_container
assert request_container.resolve(Container) is request_container  # the child, not the APP root
```

The same holds for type-based injection: a creator with a `Container` parameter receives the
container that is resolving it. This means request-scoped code reaches the request container (and its
context/cache), while app-scoped code reaches the app container.

## Context Propagation

Context never propagates between containers. A `ContextProvider` reads the context registry of the container **at the provider's own scope** — build order is irrelevant.

!!! warning "Scope determines which container is read, not timing"
    Setting context on a parent container never reaches a child-scoped provider, regardless of when you call `set_context`:

    ```python
    # ❌ Broken: MyContext provider has scope=Scope.REQUEST, so it reads the REQUEST
    # container's registry. Setting it on the APP parent has no effect.
    app_container = Container()
    app_container.set_context(MyContext, value)  # ignored for REQUEST-scoped providers
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    ```

    For a REQUEST-scoped `ContextProvider`, set the value on the request container:

    ```python
    # Option A: pass context directly when building the child
    request_container = app_container.build_child_container(
        scope=Scope.REQUEST, context={MyContext: value}
    )

    # Option B: set on the request container after building it
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.set_context(MyContext, value)
    ```

    Setting context on the parent only works when the `ContextProvider`'s scope matches the parent's scope.

## Advanced

Lower-level public surface for library authors and advanced use-cases.

### `Container` attributes and methods

- **`find_container(scope)`** — walks `scope_map` and returns the container registered at
  `scope`; raises `ScopeNotInitializedError` or `ScopeSkippedError` if the scope is absent.
- **`parent_container`** — constructor kwarg and slot; the direct parent of a child container,
  or `None` for a root. Passing a `scope ≤ parent.scope` raises `InvalidChildScopeError`.
- **`scope_map`** — `dict[IntEnum, Container]` mapping every scope in the chain to its
  container; built at construction time and inherited (plus the new scope) by each child.
- **`lock`** — a `threading.RLock` instance, or `None` when the container was created with
  `use_lock=False`. The lock gates singleton creation inside `Factory.resolve`.

### `Group.get_providers()`

`Group.get_providers()` is a classmethod that traverses the MRO (excluding `Group` and
`object`) and collects every class attribute that is an `AbstractProvider` instance, respecting
MRO override order (subclass attribute shadows parent attribute of the same name). Use it to
inspect or iterate all providers declared on a group hierarchy.

### Subclassing `AbstractProvider`

To implement a custom provider, subclass `AbstractProvider` and implement:

- **`resolve(container)`** *(required)* — returns the resolved instance.
- **`get_dependencies(container)`** *(optional)* — returns a `dict[str, AbstractProvider]`
  mapping parameter names to their providers; used by `Container.validate()` for graph
  traversal.
- **`iter_validation_issues(container)`** *(optional)* — yields `Exception` instances for
  validation-time problems found in this provider; default yields nothing.
- **`effective_scope(container)`** *(optional override)* — override this method to report the
  scope of whatever the provider ultimately resolves to. A transparent or redirect provider (like
  `Alias`) should override it to follow the source chain so that `Container.validate()` checks
  callers against the real target scope rather than any nominal scope on the wrapper itself.

### `CacheSettings.is_async_finalizer`

`CacheSettings.is_async_finalizer` is a computed bool field set at construction time via
`inspect.iscoroutinefunction(finalizer)`. `Factory.resolve` and the cache registry use it to
decide whether to `await` the finalizer during `close_async()` or treat it as sync.
