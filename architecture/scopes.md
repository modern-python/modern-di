# Scopes

`Scope` is an `IntEnum` defined in `modern_di/scope.py`. It has five named levels:

```
APP = 1  →  SESSION = 2  →  REQUEST = 3  →  ACTION = 4  →  STEP = 5
```

Higher integer values represent deeper (more short-lived) scopes. The ordering is significant: the integer value
determines both the scope hierarchy and the validity rules for provider resolution.

## Resolution rule

Every provider is bound to a scope at declaration time. The rule is:

> A provider bound to scope **S** may only be resolved from a container whose scope is **S or deeper**
> (i.e., `container.scope >= provider.scope`).

Attempting to resolve a provider from a container whose scope is shallower than the provider's scope raises one of
two exceptions, depending on what went wrong:

- **`ScopeNotInitializedError`** — raised when the required scope is deeper than the resolving container's scope
  (the child container for that scope has not been built yet). Message shape:

  ```
  Provider of scope {provider_scope} cannot be resolved in container of scope {container_scope}.
  ```

- **`ScopeSkippedError`** — raised when the required scope is shallower than the resolving container's scope but
  is not present anywhere in the ancestor chain (i.e., the chain was started at a scope that skipped it). Message
  shape:

  ```
  No {provider_scope}-scope container exists in this chain; this chain starts at {container_scope}.
  Build a {provider_scope}-scope container as the root.
  ```

Both exceptions inherit from `ContainerError → ModernDIError → RuntimeError`.

## How the container locates the right-scope container

Each `Container` maintains a `scope_map: dict[IntEnum, Container]`. When a root container is created, the map is
`{scope: self}`. Each child container extends the map: `{**parent.scope_map, child_scope: child}`.

`Container.find_container(scope)` performs the lookup:

1. If `scope` is in `scope_map`, return the corresponding container immediately — no tree walk needed.
2. If `scope` is not in `scope_map` and `scope > self.scope`, raise `ScopeNotInitializedError` (the required
   child container has not been built yet).
3. If `scope` is not in `scope_map` and `scope <= self.scope`, raise `ScopeSkippedError` (the scope was
   never present in this chain).

The `scope_map` is built incrementally at construction time, so lookups are O(1). There is no runtime
parent-chain traversal during resolution.

## Custom scopes

`Scope` is a convenience enum, but `Container` accepts any `enum.IntEnum` member as its scope. Teams that need
more levels (or different names) can define their own `IntEnum` and use it throughout. The same integer-ordering
rules apply. Passing a non-`IntEnum` value raises `InvalidScopeTypeError`.

## Worked example

```python
from modern_di import Container, Scope
from modern_di import providers

class AppGroup(Group):
    # Resolved once and cached for the lifetime of the app container.
    db_pool = providers.Factory(scope=Scope.APP, creator=DatabasePool, cache_settings=CacheSettings())

    # Resolved once per request container.
    current_user = providers.Factory(scope=Scope.REQUEST, creator=UserFromRequest)

# Root container at APP scope.
app_container = Container(scope=Scope.APP, groups=[AppGroup])

# Works: db_pool is APP-scoped, container is APP-scoped (same scope).
pool = app_container.resolve(DatabasePool)

# Fails: current_user is REQUEST-scoped, but the container is APP-scoped (too shallow).
# Raises ScopeNotInitializedError:
#   "Provider of scope REQUEST cannot be resolved in container of scope APP."
app_container.resolve(UserFromRequest)  # raises

# Build a child container for the request boundary.
request_container = app_container.build_child_container(scope=Scope.REQUEST, context={...})

# Works: current_user is REQUEST-scoped, container is REQUEST-scoped.
user = request_container.resolve(UserFromRequest)

# Works: db_pool is APP-scoped; find_container(APP) returns the parent app_container via scope_map.
pool_again = request_container.resolve(DatabasePool)
```

`build_child_container` enforces that the child scope is strictly deeper than the parent scope. Passing a scope
with a lower or equal integer value raises `InvalidChildScopeError`:

```
Scope of child container cannot be {child_scope} if parent scope is {parent_scope}
(child scope value must be strictly greater than parent scope value).
Possible scopes are {allowed_scopes}.
```

Calling `build_child_container()` with no `scope` argument auto-increments to the next integer in the same
`IntEnum` class. If the parent is already at the maximum defined value, `MaxScopeReachedError` is raised.
