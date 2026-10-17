# AsyncCreatorError

## Symptom

```
modern_di.exceptions.registration.AsyncCreatorError: Factory creator create_http_client is async, but resolution is synchronous, so resolve() would return an un-awaited coroutine. Build the resource in your framework's lifespan and hand it to the container with set_context() and a ContextProvider: https://modern-di.modern-python.org/recipes/async-lifespan/
See: https://modern-di.modern-python.org/troubleshooting/async-creator-error/
```

The `Factory(...)` call raises it before any container exists, with or without
`skip_creator_parsing=True`. The exception carries `.creator`.

## Cause

The creator passed to `Factory` returns a coroutine when called. `modern-di` resolves
synchronously, so it can never await that coroutine, and `resolve()` would hand back the coroutine
object instead of the resource.

The check catches three shapes:

- An `async def` function or method.
- A `functools.partial` around an `async def` function.
- An instance of a class whose `__call__` is `async def`.

A class is accepted even when its `__call__` is async, because calling the class builds an instance
synchronously. A sync function that returns an awaitable is also accepted, since nothing short of
calling it shows what it returns.

## Fix

Await the resource outside the container, in the framework's lifespan, and register the live object
with `container.set_context()` behind a `ContextProvider`. The
[async lifespan recipe](../recipes/async-lifespan.md) shows the full pattern with FastAPI.

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class HttpClient: ...


async def create_http_client() -> HttpClient:
    return HttpClient()
-->

<!-- raises: AsyncCreatorError -->

```python
# Broken:
providers.Factory(create_http_client, scope=Scope.APP)
```

```python
# Works:
class Dependencies(Group):
    http_client = providers.ContextProvider(HttpClient, scope=Scope.APP)


container = Container(groups=[Dependencies])
container.set_context(HttpClient, await create_http_client())
assert isinstance(container.resolve(HttpClient), HttpClient)
```

If the client builds without an `await` and only its cleanup is async, keep a sync creator and give
it an async finalizer instead; see
[When a sync creator works instead](../recipes/async-lifespan.md#when-a-sync-creator-works-instead).

## See also

- [Async resources via lifespan](../recipes/async-lifespan.md): building async resources outside the container.
- [Context providers](../providers/context.md): `ContextProvider` and `set_context` in depth.
- [Lifecycle](../providers/lifecycle.md): async finalizers and `close_async()`.
