# modern-di for FastAPI users

FastAPI's own `Depends` system covers a single request-scoped web service well. You reach for
modern-di once you need a second entrypoint (a worker, a CLI), typed app-wide singletons with real
teardown, or overrides that work outside the HTTP path — see
[Do you even need a DI container?](comparison.md#do-you-even-need-a-di-container). This page
translates the `Depends` idioms you already know into their modern-di equivalents.

## Translation table

| FastAPI `Depends` | modern-di | Notes |
|---|---|---|
| `Depends(fn)` | `Factory(fn)` | Both auto-wire the callable's parameters; modern-di matches by type annotation instead of by the callable's own parameter defaults. |
| bare `Depends(fn)` (`use_cache=True`, the default) | `Factory(fn, scope=Scope.REQUEST, cache=True)` | FastAPI memoizes a dependency for the rest of the *same request* once it's been called; the REQUEST-scoped cached `Factory` is the equivalent — one shared instance per request container. |
| `Depends(fn, use_cache=False)` | a bare `Factory(fn)` — no `cache` | Without `cache`, a `Factory` builds a fresh instance on every resolve, matching `use_cache=False`. |
| `yield`-based teardown (`def fn(): ...; yield x; ...cleanup...`) | `cache=CacheSettings(finalizer=cleanup_fn)` | modern-di has no generator-creator form (see [Design decisions](design-decisions.md)); teardown is a second, explicit object instead of code after `yield`. `finalizer` may be sync or async — see [Lifecycle](../providers/lifecycle.md). |
| `@lru_cache`-wrapped dependency (process-wide singleton) | `Factory(fn, scope=Scope.APP, cache=True)`, optionally with a `finalizer` | `lru_cache` has no cleanup hook; the APP-scoped cached `Factory` adds one via `CacheSettings(finalizer=...)` if the singleton needs to release anything on shutdown. |
| `app.dependency_overrides[fn] = fake` | `container.override(provider, fake)` | modern-di overrides are keyed by **provider reference**, not by callable, and apply across the whole container tree — see [Testing with overrides](../recipes/testing-overrides.md). Reset with `container.reset_override(provider)`. |
| the manual `try`/`finally` reset FastAPI's docs recommend around `dependency_overrides` | `with container.override(provider, fake) as mock: ...` | Auto-resets on exit instead of a hand-written `finally`. See [Testing with overrides](../recipes/testing-overrides.md) for the full semantics. |

## Two meanings of "scope"

Since FastAPI 0.121.0, `Depends(scope="function" | "request")` controls **when the code after
`yield` runs** relative to the response: `scope="function"` tears down right after your path
operation function returns (before the response is sent), and `scope="request"` — the default for
a `yield` dependency — tears down after the response has been sent back to the client. It says
nothing about how many times the dependency is *constructed*; that's `use_cache`'s job.

modern-di's `Scope` (`APP → SESSION → REQUEST → ACTION → STEP`) answers a different question
entirely: **how long a provider's cached instance lives**, not when its finalizer fires relative to
a response. The two `scope`s share a word but not an axis — FastAPI's is teardown timing, modern-di's
is lifetime. See [Scopes](../providers/scopes.md) for the full model.

## Example: request-scoped session with teardown

```python
import dataclasses

from modern_di import Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class Session:
    connection_string: str


def create_session() -> Session:
    return Session(connection_string="postgresql+asyncpg://localhost/app")


def close_session(session: Session) -> None:
    ...  # release the connection


class Dependencies(Group):
    session = providers.Factory(
        create_session,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=close_session),
    )
```

This is the modern-di equivalent of a FastAPI `yield`-dependency that hands out one session per
request and closes it afterward — but with the container's finalizer, not code after `yield`, and
`Scope.REQUEST` naming the lifetime rather than the teardown moment.

## See also

- [modern-di vs other libraries](comparison.md) — including the cross-framework vocabulary table.
- [FastAPI integration](../integrations/fastapi.md) — `setup_di`, `FromDI`, and websocket scopes.
- [Design decisions](design-decisions.md) — why modern-di has no generator-based teardown.
